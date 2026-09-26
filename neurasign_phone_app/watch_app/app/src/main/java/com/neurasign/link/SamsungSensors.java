package com.neurasign.link;

import android.content.Context;
import android.content.pm.PackageManager;
import android.os.*;
import java.lang.reflect.*;
import java.util.*;
import java.util.function.Consumer;
import org.json.*;

/** Optional official SDK binding. Missing SDK/policy/permissions never produce data.
 * Reflection lets the same base APK collect standard Wear OS sensors without
 * redistributing Samsung's account-gated binary. See README for the Samsung build.
 */
final class SamsungSensors {
  interface Sink { void accept(String source, String metric, String unit, long time, double value); }
  private static final String ROOT = "com.samsung.android.service.health.tracking.";
  private static final Map<String, String[][]> CHANNELS = new LinkedHashMap<>();
  static {
    CHANNELS.put("HEART_RATE_CONTINUOUS", new String[][]{{"heart_rate","bpm"},{"heart_rate_status","code"},{"ppi_interval","ms"},{"ppi_status","code"}});
    CHANNELS.put("PPG_CONTINUOUS", new String[][]{{"ppg_green","a.u."},{"ppg_ir","a.u."},{"ppg_red","a.u."},{"ppg_green_status","code"},{"ppg_ir_status","code"},{"ppg_red_status","code"}});
    CHANNELS.put("EDA_CONTINUOUS", new String[][]{{"electrodermal_conductance","µS"},{"eda_status","code"}});
    CHANNELS.put("SKIN_TEMPERATURE_CONTINUOUS", new String[][]{{"skin_temperature","°C"},{"sensor_temperature","°C"},{"skin_temperature_status","code"}});
    CHANNELS.put("ECG_ON_DEMAND", new String[][]{{"electrocardiogram","mV"},{"ecg_contact","code"},{"ecg_sequence","count"},{"ppg_green","a.u."}});
    CHANNELS.put("SPO2_ON_DEMAND", new String[][]{{"oxygen_saturation","%"},{"oxygen_status","code"},{"heart_rate","bpm"}});
  }
  private final Context context;
  private final Handler handler;
  private final Sink sink;
  private final Consumer<String> warning;
  private final ArrayList<String> warnings = new ArrayList<>();
  private final Map<String, Object> trackers = new LinkedHashMap<>();
  private final Set<String> listening = new HashSet<>();
  private final Map<String, Runnable> demandTimeouts = new HashMap<>();
  private Object service;
  private boolean ready = false, frozen = false, closed = false;
  SamsungSensors(Context context, Handler handler, Sink sink, Consumer<String> warning) { this.context = context; this.handler = handler; this.sink = sink; this.warning = warning; }
  private static Class<?> type(String name) throws ClassNotFoundException { return Class.forName(ROOT + name); }
  private static Object call(Object target, String method) throws ReflectiveOperationException { return target.getClass().getMethod(method).invoke(target); }
  private static Object enumValue(Class<?> type, String name) { return Arrays.stream(type.getEnumConstants()).filter(value -> ((Enum<?>)value).name().equals(name)).findFirst().orElseThrow(); }
  private void warn(String message) { if (!warnings.contains(message) && warnings.size() < 20) warnings.add(message); warning.accept(message); }
  boolean ready() { return ready; }
  List<String> warnings() { return List.copyOf(warnings); }
  void connect() {
    if (!Build.MANUFACTURER.equalsIgnoreCase("samsung")) { ready = true; return; }
    try {
      Class<?> listenerType = type("ConnectionListener");
      Object listener = Proxy.newProxyInstance(listenerType.getClassLoader(), new Class<?>[]{listenerType}, (proxy, method, args) -> {
        if (method.getDeclaringClass() == Object.class) return proxyObject(proxy, method, args);
        handler.post(() -> {
          if (closed) return;
          if (method.getName().equals("onConnectionSuccess")) discover();
          else { ready = true; warn("Samsung sensor service unavailable. Check SDK policy and developer mode."); stop(); }
        });
        return null;
      });
      service = type("HealthTrackingService").getConstructor(listenerType, Context.class).newInstance(listener, context);
      call(service, "connectService");
    } catch (ClassNotFoundException e) { ready = true; warn("Samsung raw channels require the Samsung SDK build."); }
    catch (ReflectiveOperationException | RuntimeException e) { ready = true; warn("Samsung sensor service could not connect."); }
  }
  private static Object proxyObject(Object proxy, Method method, Object[] args) { return switch(method.getName()) { case "hashCode" -> System.identityHashCode(proxy); case "equals" -> proxy == args[0]; default -> "NeurasignSensorListener"; }; }
  private void discover() {
    if (frozen) { ready = true; warn("Samsung connected after setup. Reconnect to add its channels."); return; }
    try {
      Object capability = call(service, "getTrackingCapability");
      List<?> supported = (List<?>)call(capability, "getSupportHealthTrackerTypes");
      Class<?> trackerType = type("data.HealthTrackerType");
      for (Object tracker : supported) {
        String name = ((Enum<?>)tracker).name();
        if (!CHANNELS.containsKey(name)) continue;
        String permission = "android.permission.BODY_SENSORS";
        if (context.checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED) { warn("Allow sensor access for Samsung channels."); continue; }
        try {
          Object instance;
          if (name.startsWith("PPG")) {
            Class<?> ppgType = type("data.PpgType");
            Set<Object> colors = new HashSet<>();
            for (String color : new String[]{"GREEN", "IR", "RED"}) colors.add(enumValue(ppgType, color));
            instance = service.getClass().getMethod("getHealthTracker", trackerType, Set.class).invoke(service, tracker, colors);
          } else instance = service.getClass().getMethod("getHealthTracker", trackerType).invoke(service, tracker);
          trackers.put(name, instance);
        } catch (ReflectiveOperationException | RuntimeException e) { warn("Samsung channel unavailable: " + name); }
      }
      ready = true;
    } catch (ReflectiveOperationException | RuntimeException e) { ready = true; warn("Could not read Samsung sensor capabilities."); }
  }
  List<JSONObject> sources() throws JSONException {
    frozen = true;
    var output = new ArrayList<JSONObject>();
    for (boolean demand : new boolean[]{false, true}) {
      JSONArray caps = new JSONArray(); Set<String> metrics = new HashSet<>();
      for (String tracker : trackers.keySet()) if (tracker.endsWith("ON_DEMAND") == demand) {
        for (String[] channel : CHANNELS.get(tracker)) if (metrics.add(channel[0])) caps.put(Frames.capability(channel[0], channel[1], "samsung-health-sensor-1.4:" + (demand ? "on-demand" : "continuous")));
      }
      if (caps.length() > 0) output.add(new JSONObject().put("id", demand ? "samsung-on-demand" : "samsung-continuous").put("name", demand ? "Samsung spot measurements" : "Samsung sensors").put("capabilities", caps));
    }
    return output;
  }
  void start() { for (String name : trackers.keySet()) if (!name.endsWith("ON_DEMAND")) listen(name); }
  void measure(String name) {
    if (!name.equals("ECG_ON_DEMAND") && !name.equals("SPO2_ON_DEMAND")) return;
    if (!trackers.containsKey(name)) { warn("This measurement is unavailable on this watch/build."); return; }
    // On-demand operations require wearer action and have explicit bounded lifetimes.
    for (String active : List.copyOf(listening)) if (active.endsWith("ON_DEMAND")) unlisten(active);
    listen(name);
    Runnable timeout = () -> unlisten(name); demandTimeouts.put(name, timeout);
    handler.postDelayed(timeout, name.startsWith("ECG") ? 30000 : 60000);
  }
  private void listen(String name) {
    if (closed || listening.contains(name)) return;
    try {
      Class<?> listenerType = type("HealthTracker$TrackerEventListener");
      Object listener = Proxy.newProxyInstance(listenerType.getClassLoader(), new Class<?>[]{listenerType}, (proxy, method, args) -> {
        if (method.getDeclaringClass() == Object.class) return proxyObject(proxy, method, args);
        if (method.getName().equals("onDataReceived")) {
          List<?> points = new ArrayList<>((List<?>)args[0]);
          handler.post(() -> { if (closed || !listening.contains(name)) return; try { for (Object point : points) decode(name, point); } catch (ReflectiveOperationException | RuntimeException e) { warn("Samsung data rejected: " + name); unlisten(name); } });
        } else if (method.getName().equals("onError")) handler.post(() -> { if (closed || !listening.contains(name)) return; warn("Samsung channel stopped: " + name + " · " + String.valueOf(args[0])); unlisten(name); });
        return null;
      });
      trackers.get(name).getClass().getMethod("setEventListener", listenerType).invoke(trackers.get(name), listener);
      listening.add(name);
    } catch (ReflectiveOperationException | RuntimeException e) { warn("Samsung tracking could not start: " + name); }
  }
  private static Object value(Object point, String group, String field) throws ReflectiveOperationException {
    Object key = type("data.ValueKey$" + group).getField(field).get(null);
    return point.getClass().getMethod("getValue", type("data.ValueKey")).invoke(point, key);
  }
  private static double number(Object point, String group, String field) throws ReflectiveOperationException {
    Object result = value(point, group, field);
    if (!(result instanceof Number n) || !Double.isFinite(n.doubleValue())) throw new IllegalArgumentException("Missing sensor value");
    return n.doubleValue();
  }
  private void emit(String source, String metric, String unit, long time, double value) { sink.accept(source, metric, unit, time, value); }
  private void decode(String tracker, Object point) throws ReflectiveOperationException {
    long time = ((Number)call(point, "getTimestamp")).longValue();
    // Do not relabel an unknown clock as UTC or turn a delayed batch into live data.
    if (time < System.currentTimeMillis() - 86400000 || time > System.currentTimeMillis() + 5000) throw new IllegalArgumentException("Unrecognized Samsung timestamp");
    String source = tracker.endsWith("ON_DEMAND") ? "samsung-on-demand" : "samsung-continuous";
    switch(tracker) {
      case "HEART_RATE_CONTINUOUS" -> {
        double status = number(point, "HeartRateSet", "HEART_RATE_STATUS"); emit(source, "heart_rate_status", "code", time, status);
        if (status == 1) emit(source, "heart_rate", "bpm", time, number(point, "HeartRateSet", "HEART_RATE"));
        Object intervals = value(point, "HeartRateSet", "IBI_LIST"), flags = value(point, "HeartRateSet", "IBI_STATUS_LIST");
        if (intervals instanceof List<?> values && flags instanceof List<?> states && values.size() == states.size()) {
          for (int i = 0; i < values.size(); i++) {
            emit(source, "ppi_interval", "ms", time, ((Number)values.get(i)).doubleValue());
            emit(source, "ppi_status", "code", time, ((Number)states.get(i)).doubleValue());
          }
        }
      }
      case "PPG_CONTINUOUS" -> {
        for (String color : new String[]{"GREEN", "IR", "RED"}) {
          double status = number(point, "PpgSet", color + "_STATUS"); String metric = "ppg_" + color.toLowerCase(Locale.ROOT);
          emit(source, metric + "_status", "code", time, status);
          if (status == 0) emit(source, metric, "a.u.", time, number(point, "PpgSet", "PPG_" + color));
        }
      }
      case "EDA_CONTINUOUS" -> {
        double status = number(point, "EdaSet", "STATUS"); emit(source, "eda_status", "code", time, status);
        if (status == 0) emit(source, "electrodermal_conductance", "µS", time, number(point, "EdaSet", "SKIN_CONDUCTANCE"));
      }
      case "SKIN_TEMPERATURE_CONTINUOUS" -> {
        double status = number(point, "SkinTemperatureSet", "STATUS"); emit(source, "skin_temperature_status", "code", time, status);
        if (status == 0) { emit(source, "skin_temperature", "°C", time, number(point, "SkinTemperatureSet", "OBJECT_TEMPERATURE")); emit(source, "sensor_temperature", "°C", time, number(point, "SkinTemperatureSet", "AMBIENT_TEMPERATURE")); }
      }
      case "ECG_ON_DEMAND" -> {
        double lead = number(point, "EcgSet", "LEAD_OFF"), sample = number(point, "EcgSet", "ECG_MV");
        emit(source, "ecg_contact", "code", time, lead); emit(source, "ecg_sequence", "count", time, number(point, "EcgSet", "SEQUENCE"));
        if (lead == 0 && sample >= number(point, "EcgSet", "MIN_THRESHOLD_MV") && sample <= number(point, "EcgSet", "MAX_THRESHOLD_MV")) emit(source, "electrocardiogram", "mV", time, sample);
        emit(source, "ppg_green", "a.u.", time, number(point, "EcgSet", "PPG_GREEN"));
      }
      case "SPO2_ON_DEMAND" -> {
        double status = number(point, "SpO2Set", "STATUS"); emit(source, "oxygen_status", "code", time, status);
        if (status == 2) { emit(source, "oxygen_saturation", "%", time, number(point, "SpO2Set", "SPO2")); emit(source, "heart_rate", "bpm", time, number(point, "SpO2Set", "HEART_RATE")); unlisten(tracker); }
      }
      default -> throw new IllegalArgumentException("Unsupported Samsung tracker");
    }
  }
  void flush() { for (String name : List.copyOf(listening)) if (!name.endsWith("ON_DEMAND")) try { call(trackers.get(name), "flush"); } catch (ReflectiveOperationException ignored) { } }
  private void unlisten(String name) {
    Runnable timeout = demandTimeouts.remove(name); if (timeout != null) handler.removeCallbacks(timeout);
    if (listening.remove(name)) try { call(trackers.get(name), "unsetEventListener"); } catch (ReflectiveOperationException ignored) { }
  }
  private void stop() { for (String name : List.copyOf(listening)) unlisten(name); }
  void close() { closed = true; stop(); if (service != null) try { call(service, "disconnectService"); } catch (ReflectiveOperationException ignored) { } }
}
