package com.neurasign.link;

import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.hardware.*;
import android.os.*;
import com.google.android.gms.wearable.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.json.*;

public final class SensorService extends Service implements SensorEventListener, MessageClient.OnMessageReceivedListener {
  public static volatile String status = "Tap Start, then connect from your phone.";
  public static volatile boolean running = false;
  private static final String PATH = "/neurasign/link/v1";
  private final Handler handler = new Handler(Looper.getMainLooper());
  private SensorManager sensors;
  private final Map<Integer, Sensor> available = new LinkedHashMap<>();
  private final Frames frames = new Frames();
  private final LinkedHashMap<Long, String> awaiting = new LinkedHashMap<>();
  private final Map<Long, Long> sentAt = new HashMap<>();
  private String node, session;
  private long leaseAt, sequence, armedAt, lastRetry;
  private SamsungSensors samsung;
  private JSONArray sources;
  private boolean destroying;
  @Override public void onCreate() {
    super.onCreate(); running = true; armedAt = SystemClock.elapsedRealtime();
    var notifications = getSystemService(NotificationManager.class);
    notifications.createNotificationChannel(new NotificationChannel("capture", "Wearable connection", NotificationManager.IMPORTANCE_LOW));
    var stop = PendingIntent.getService(this, 1, new Intent(this, SensorService.class).setAction("STOP"), PendingIntent.FLAG_IMMUTABLE);
    var open = PendingIntent.getActivity(this, 2, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE);
    startForeground(1, new Notification.Builder(this, "capture").setContentTitle("NEURASIGN Link")
      .setContentText("Watch connection active · tap to stop").setSmallIcon(android.R.drawable.ic_menu_mylocation).setOngoing(true).setContentIntent(open)
      .addAction(new Notification.Action.Builder(null, "Stop", stop).build()).build());
    sensors = getSystemService(SensorManager.class);
    for (int type : new int[]{Sensor.TYPE_ACCELEROMETER, Sensor.TYPE_GYROSCOPE, Sensor.TYPE_MAGNETIC_FIELD, Sensor.TYPE_PRESSURE, Sensor.TYPE_AMBIENT_TEMPERATURE, Sensor.TYPE_HEART_RATE}) {
      if (type == Sensor.TYPE_HEART_RATE && checkSelfPermission("android.permission.BODY_SENSORS") != PackageManager.PERMISSION_GRANTED) continue;
      Sensor sensor = sensors.getDefaultSensor(type); if (sensor != null) available.put(type, sensor);
    }
    samsung = new SamsungSensors(this, handler, (source, metric, unit, time, value) -> {
      if (session != null && !destroying) try { frames.add(source, metric, unit, time, value); } catch (RuntimeException e) { fail(e.getMessage()); }
    }, this::warning);
    samsung.connect();
    Wearable.getMessageClient(this).addListener(this).addOnFailureListener(e -> fail("Wear OS phone service is unavailable."));
    status = "Ready · connect from your phone."; handler.post(tick);
  }
  @Override public int onStartCommand(Intent intent, int flags, int startId) {
    if (intent != null && "STOP".equals(intent.getAction())) { stopSelf(); return START_NOT_STICKY; }
    if (intent != null && intent.getAction() != null) {
      if (session == null) status = "Connect your phone before measuring.";
      else samsung.measure(intent.getAction());
    }
    return START_NOT_STICKY;
  }
  private void warning(String message) {
    status = message;
    if (session != null) try { send(new JSONObject().put("kind", "warning").put("message", message)); } catch (JSONException ignored) { }
  }
  private void fail(String message) {
    status = message == null ? "Watch collection stopped." : message;
    if (session != null) try { send(new JSONObject().put("kind", "error").put("message", status)); } catch (JSONException ignored) { }
    stopSelf();
  }
  private JSONArray platformCapabilities() throws JSONException {
    JSONArray caps = new JSONArray();
    for (int type : available.keySet()) {
      String[] names = names(type);
      for (String metric : names) caps.put(Frames.capability(metric, unit(type), "android-sensor-" + type));
    }
    return caps;
  }
  private static String[] names(int type) {
    String prefix = switch(type) { case Sensor.TYPE_ACCELEROMETER -> "acceleration"; case Sensor.TYPE_GYROSCOPE -> "angular_velocity"; case Sensor.TYPE_MAGNETIC_FIELD -> "magnetic_field"; default -> null; };
    if (prefix != null) return new String[]{prefix + "_x", prefix + "_y", prefix + "_z"};
    return new String[]{switch(type) { case Sensor.TYPE_HEART_RATE -> "heart_rate"; case Sensor.TYPE_PRESSURE -> "barometric_pressure"; default -> "sensor_temperature"; }};
  }
  private static String unit(int type) { return switch(type) { case Sensor.TYPE_ACCELEROMETER -> "m/s²"; case Sensor.TYPE_GYROSCOPE -> "°/s"; case Sensor.TYPE_MAGNETIC_FIELD -> "gauss"; case Sensor.TYPE_HEART_RATE -> "bpm"; case Sensor.TYPE_PRESSURE -> "hPa"; default -> "°C"; }; }
  private void begin(String sender, String requested) throws JSONException {
    if (!requested.matches("[A-Za-z0-9_-]{8,80}")) throw new JSONException("Invalid session");
    if (session != null) {
      if (!session.equals(requested) || !node.equals(sender)) { fail("Connection changed. Tap Start to reconnect."); return; }
      hello(); return;
    }
    if (!samsung.ready() && SystemClock.elapsedRealtime() - armedAt < 8000) { handler.postDelayed(() -> { try { begin(sender, requested); } catch (JSONException e) { fail("Invalid capabilities"); } }, 500); return; }
    node = sender; session = requested; leaseAt = SystemClock.elapsedRealtime(); sequence = 0;
    sources = new JSONArray();
    JSONArray platform = platformCapabilities();
    if (platform.length() > 0) sources.put(new JSONObject().put("id", "wear-os-sensors").put("name", "Watch sensors").put("capabilities", platform));
    for (JSONObject source : samsung.sources()) sources.put(source);
    if (sources.length() == 0) { fail("No supported sensors are accessible. Check permissions."); return; }
    hello();
    for (Sensor sensor : available.values()) {
      try { if (!sensors.registerListener(this, sensor, 20000, 0, handler)) warning("Sensor unavailable: " + sensor.getName()); }
      catch (SecurityException e) { warning("Sensor permission missing: " + sensor.getName()); }
    }
    samsung.start(); status = "Sending watch measurements.";
  }
  private void hello() throws JSONException { send(new JSONObject().put("kind", "hello").put("manufacturer", Build.MANUFACTURER).put("model", Build.MODEL).put("sources", sources).put("warnings", new JSONArray(samsung.warnings()))); }
  @Override public void onMessageReceived(MessageEvent event) {
    if (!PATH.equals(event.getPath()) || event.getData().length > 10000) return;
    handler.post(() -> {
      if (destroying) return;
      try {
        JSONObject message = new JSONObject(new String(event.getData(), StandardCharsets.UTF_8));
        if (message.optInt("version") != 1) return;
        String kind = message.optString("kind"), requested = message.optString("session");
        if (kind.equals("start")) { begin(event.getSourceNodeId(), requested); return; }
        if (session == null || !session.equals(requested) || !event.getSourceNodeId().equals(node)) return;
        if (kind.equals("lease")) { leaseAt = SystemClock.elapsedRealtime(); send(new JSONObject().put("kind", "heartbeat")); }
        else if (kind.equals("stop")) { status = "Sharing stopped by phone."; stopSelf(); }
        else if (kind.equals("ack")) { long id = message.getLong("sequence"); awaiting.remove(id); sentAt.remove(id); }
      } catch (JSONException e) { fail("Invalid phone protocol message."); }
    });
  }
  @Override public void onSensorChanged(SensorEvent event) {
    if (session == null || destroying || event.accuracy == SensorManager.SENSOR_STATUS_UNRELIABLE) return;
    int type = event.sensor.getType();
    if (type == Sensor.TYPE_HEART_RATE && event.values[0] <= 0) return;
    long time = System.currentTimeMillis() + (event.timestamp - SystemClock.elapsedRealtimeNanos()) / 1000000;
    String[] metrics = names(type);
    double factor = type == Sensor.TYPE_GYROSCOPE ? 180 / Math.PI : type == Sensor.TYPE_MAGNETIC_FIELD ? .01 : 1;
    try { for (int i = 0; i < metrics.length; i++) frames.add("wear-os-sensors", metrics[i], unit(type), time, event.values[i] * factor); }
    catch (RuntimeException e) { fail(e.getMessage()); }
  }
  @Override public void onAccuracyChanged(Sensor sensor, int accuracy) { }
  private final Runnable tick = new Runnable() { public void run() {
    if (destroying) return;
    long now = SystemClock.elapsedRealtime();
    if (session == null && now - armedAt > 120000) { fail("No phone connected. Tap Start to try again."); return; }
    if (session != null) {
      if (now - leaseAt > 30000) { fail("Phone connection expired. Collection stopped."); return; }
      try {
        samsung.flush();
        for (JSONObject frame : frames.drain()) {
          if (awaiting.size() >= 64) { fail("Phone is not acknowledging samples. Collection stopped."); return; }
          frame.put("version", 1).put("kind", "samples").put("session", session).put("sequence", sequence);
          String payload = frame.toString();
          if (payload.getBytes(StandardCharsets.UTF_8).length > 100000) { fail("Watch sample message is too large."); return; }
          awaiting.put(sequence, payload); sentAt.put(sequence, now); sequence++; transmit(payload);
        }
        if (now - lastRetry > 2000) {
          lastRetry = now;
          for (var entry : awaiting.entrySet()) {
            if (now - sentAt.get(entry.getKey()) > 20000) { fail("Phone stopped acknowledging samples."); return; }
            if (now - sentAt.get(entry.getKey()) > 2000) transmit(entry.getValue());
          }
        }
      } catch (Exception e) { fail("Watch sample encoding failed: " + e.getClass().getSimpleName()); return; }
    }
    handler.postDelayed(this, 750);
  }};
  private void send(JSONObject message) throws JSONException { message.put("version", 1).put("session", session); transmit(message.toString()); }
  private void transmit(String payload) { if (node != null) Wearable.getMessageClient(this).sendMessage(node, PATH, payload.getBytes(StandardCharsets.UTF_8)); }
  @Override public void onDestroy() {
    if (session != null) try { send(new JSONObject().put("kind", "error").put("message", "Watch collection stopped. Tap Start on the watch to reconnect.")); } catch (JSONException ignored) { }
    destroying = true; running = false; handler.removeCallbacksAndMessages(null);
    if (sensors != null) sensors.unregisterListener(this);
    if (samsung != null) samsung.close();
    Wearable.getMessageClient(this).removeListener(this);
    frames.clear(); awaiting.clear(); sentAt.clear(); session = null; node = null;
    if (status.startsWith("Sending") || status.startsWith("Ready")) status = "Collection stopped.";
    stopForeground(STOP_FOREGROUND_REMOVE); super.onDestroy();
  }
  @Override public IBinder onBind(Intent intent) { return null; }
}
