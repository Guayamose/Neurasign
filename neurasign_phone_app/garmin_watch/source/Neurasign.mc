import Toybox.Application;
import Toybox.Communications;
import Toybox.Graphics;
import Toybox.Lang;
import Toybox.Sensor;
import Toybox.System;
import Toybox.Time;
import Toybox.Timer;
import Toybox.WatchUi;

class Delivery extends Communications.ConnectionListener {
    function initialize() { ConnectionListener.initialize(); }
    function onComplete() {}
    function onError() {} // Frames remain pending until the phone's persistence ACK.
}
class NeurasignApp extends Application.AppBase {
    var session = null;
    var armed = false;
    var status = "Press Start, then\nconnect your phone";
    var pending = {};
    var units = {};
    var sequence = 0;
    var lease = 0;
    var timer = null;
    var view;
    function initialize() { AppBase.initialize(); }
    function onStart(state) { Communications.registerForPhoneAppMessages(method(:onPhone)); }
    function onStop(state) { stop(true); }
    function onInactive(state) { stop(false); }
    function onActive(state) { stop(true); }
    function getInitialView() { view = new LinkView(self); return [view, new LinkInput(self)]; }
    function toggle() { if (armed) { stop(true); } else { armed = true; status = "Ready\nConnect from phone"; WatchUi.requestUpdate(); } }
    function stopSensors() { Sensor.enableSensorEvents(null); Sensor.setEnabledSensors([]); Sensor.unregisterSensorDataListener(); }
    function stop(disable) {
        if (disable) { stopSensors(); }
        if (timer != null) { timer.stop(); }
        timer = null; session = null; pending = {}; armed = false;
        status = "Sharing stopped"; WatchUi.requestUpdate();
    }
    function envelope(kind) { return {"version"=>1, "kind"=>kind, "session"=>session}; }
    function send(frame) { try { Communications.transmit(frame, null, new Delivery()); } catch(e) {} }
    function timeText() {
        var t = Time.Gregorian.utcInfo(Time.now(), Time.FORMAT_SHORT);
        return t.year.format("%04d")+"-"+t.month.format("%02d")+"-"+t.day.format("%02d")+"T"+t.hour.format("%02d")+":"+t.min.format("%02d")+":"+t.sec.format("%02d")+"Z";
    }
    function onPhone(message as Communications.PhoneAppMessage) as Void {
        var body = message.data;
        if (!(body instanceof Dictionary) || body["version"] != 1 || !(body["session"] instanceof String)) { return; }
        if (body["kind"] == "start") { if (armed && session != body["session"]) { begin(body["session"]); } return; }
        if (session == null || body["session"] != session) { return; }
        if (body["kind"] == "stop") { stop(true); }
        else if (body["kind"] == "lease") { lease = System.getTimer(); send(envelope("heartbeat")); }
        else if (body["kind"] == "ack") { pending.remove(body["sequence"]); }
    }
    function begin(id) {
        stop(true); armed = true; session = id; lease = System.getTimer(); sequence = 0;
        units = {}; var warnings = ["Watch app must stay open. Channels depend on watch hardware and firmware. No raw ECG, PPG or EDA API."];
        var enabled = Sensor.setEnabledSensors([Sensor.SENSOR_ONBOARD_HEARTRATE, Sensor.SENSOR_ONBOARD_PULSE_OXIMETRY]);
        if (enabled.indexOf(Sensor.SENSOR_ONBOARD_HEARTRATE) >= 0) { units["heart_rate"] = "bpm"; }
        if (enabled.indexOf(Sensor.SENSOR_ONBOARD_PULSE_OXIMETRY) >= 0) { units["oxygen_saturation"] = "%"; }
        var info = Sensor.getInfo();
        if (info has :temperature) { units["sensor_temperature"] = "°C"; }
        if (info has :pressure) { units["barometric_pressure"] = "hPa"; }
        var options = {:period=>1, :heartBeatIntervals=>{:enabled=>true}};
        var rawMetrics = {};
        var sensorTypes = [:accelerometer, :gyroscope, :magnetometer];
        for (var sensorIndex = 0; sensorIndex < sensorTypes.size(); sensorIndex += 1) {
            var sensor = sensorTypes[sensorIndex];
            var rate = null;
            try { if (Sensor has :getMaxSampleRateForSensorType) { rate = Sensor.getMaxSampleRateForSensorType(sensor); }
                  else if (sensor == :accelerometer) { rate = Sensor.getMaxSampleRate(); } } catch(e) {}
            if (rate != null && rate > 0) {
                options[sensor] = {:enabled=>true, :sampleRate=>rate < 25 ? rate : 25, :includeTimestamps=>true};
                var prefix = sensor == :accelerometer ? "acceleration" : (sensor == :gyroscope ? "angular_velocity" : "magnetic_field");
                var unit = sensor == :accelerometer ? "m/s²" : (sensor == :gyroscope ? "°/s" : "gauss");
                var axes = ["x", "y", "z"]; for (var i = 0; i < axes.size(); i += 1) { rawMetrics[prefix+"_"+axes[i]] = unit; }
            }
        }
        try {
            Sensor.registerSensorDataListener(method(:onData), options);
            var rawKeys = rawMetrics.keys(); for (var i = 0; i < rawKeys.size(); i += 1) { units[rawKeys[i]] = rawMetrics[rawKeys[i]]; }
            units["rr_interval"] = "ms";
        } catch(e) { warnings.add("High-rate sensor registration was rejected. Only scalar channels are active."); }
        if (units.size() == 0) { stop(true); status = "No sensor access"; return; }
        var caps = [];
        var metricKeys = units.keys(); for (var i = 0; i < metricKeys.size(); i += 1) {
            var metric = metricKeys[i];
            caps.add({"metric"=>metric,"unit"=>units[metric],"measurement_kind"=>"sample","delivery_mode"=>"stream","timestamp_basis"=>"device",
                "method"=>"garmin-watch-callback-clock; SDK relative offsets when present; untimed blocks share callback time"});
        }
        var hello = envelope("hello"); hello["manufacturer"] = "Garmin"; hello["model"] = "Connect IQ watch";
        hello["sources"] = [{"id"=>"garmin-connect-iq","name"=>"Watch sensors","capabilities"=>caps}]; hello["warnings"] = warnings;
        send(hello); Sensor.enableSensorEvents(method(:onInfo));
        timer = new Timer.Timer(); timer.start(method(:tick), 1000, true);
        status = "Sharing sensors\nPhone linked"; WatchUi.requestUpdate();
    }
    function tick() as Void {
        if (System.getTimer()-lease > 30000 || pending.size() > 12) { stop(true); status = "Phone disconnected\nReconnect to share"; return; }
        var keys = pending.keys(); if (keys.size() > 0) { send(pending[keys[0]]); }
    }
    function block(metric, values, offsets, stamp) {
        if (!units.hasKey(metric) || values.size() == 0 || values.size() > 128) { return null; }
        return {"metric"=>metric,"unit"=>units[metric],"value"=>values[values.size()-1],"measured_at"=>stamp,"samples"=>values,"sample_offsets_ms"=>offsets};
    }
    function emit(rows) {
        if (session == null || rows.size() == 0) { return; }
        if (pending.size() >= 12) { stop(true); status = "Phone buffer full\nReconnect to share"; return; }
        var frame = envelope("samples"); frame["source"] = "garmin-connect-iq"; frame["sequence"] = sequence; frame["measurements"] = rows;
        pending[sequence] = frame; sequence += 1; send(frame);
    }
    function scalar(rows, metric, value, factor, stamp) {
        if (value != null && units.hasKey(metric) && !(metric == "heart_rate" && value <= 0)) { rows.add(block(metric, [value*factor], [0], stamp)); }
    }
    function onInfo(info as Sensor.Info) as Void {
        if (session == null) { return; }
        var stamp = timeText(); var rows = [];
        scalar(rows,"heart_rate", info.heartRate, 1.0, stamp);
        if (info has :oxygenSaturation) { scalar(rows,"oxygen_saturation",info.oxygenSaturation,1.0,stamp); }
        if (info has :temperature) { scalar(rows,"sensor_temperature",info.temperature,1.0,stamp); }
        if (info has :pressure) { scalar(rows,"barometric_pressure",info.pressure,0.01,stamp); }
        emit(rows);
    }
    function axes(rows, data, prefix, factor, stamp) {
        if (data == null) { return; }
        var times = null; if (data has :timestamp) { times = data.timestamp; }
        var vectors = [data.x, data.y, data.z]; var names = ["x", "y", "z"];
        for (var axis = 0; axis < 3; axis += 1) {
            var values = vectors[axis]; if (values == null || values.size() == 0) { continue; }
            var scaled = []; var offsets = [];
            for (var i = 0; i < values.size(); i += 1) {
                scaled.add(values[i]*factor);
                offsets.add(times != null && times.size() == values.size() ? times[i]-times[times.size()-1] : 0);
            }
            var row = block(prefix+"_"+names[axis], scaled, offsets, stamp); if (row != null) { rows.add(row); }
        }
    }
    function onData(data as Sensor.SensorData) as Void {
        if (session == null) { return; }
        var rows = []; var stamp = timeText();
        if (data has :accelerometerData) { axes(rows,data.accelerometerData,"acceleration",0.00980665,stamp); }
        if (data has :gyroscopeData) { axes(rows,data.gyroscopeData,"angular_velocity",1.0,stamp); }
        if (data has :magnetometerData) { axes(rows,data.magnetometerData,"magnetic_field",0.001,stamp); }
        if (data has :heartRateData && data.heartRateData != null) {
            var input = data.heartRateData.heartBeatIntervals; var rr = []; var offsets = [];
            for (var i = 0; i < input.size(); i += 1) { if (input[i] > 0) { rr.add(input[i]); offsets.add(0); } }
            var row = block("rr_interval",rr,offsets,stamp); if (row != null) { rows.add(row); }
        }
        emit(rows);
    }
}
class LinkView extends WatchUi.View {
    var app;
    function initialize(owner) { View.initialize(); app = owner; }
    function onUpdate(dc) {
        dc.setColor(Graphics.COLOR_WHITE, Graphics.COLOR_BLACK); dc.clear();
        dc.drawText(dc.getWidth()/2, dc.getHeight()/4, Graphics.FONT_SMALL,"NEURASIGN",Graphics.TEXT_JUSTIFY_CENTER);
        dc.drawText(dc.getWidth()/2, dc.getHeight()/2, Graphics.FONT_TINY,app.status,Graphics.TEXT_JUSTIFY_CENTER);
    }
}
class LinkInput extends WatchUi.BehaviorDelegate {
    var app;
    function initialize(owner) { BehaviorDelegate.initialize(); app = owner; }
    function onSelect() { app.toggle(); return true; }
    function onTap(event) { app.toggle(); return true; }
    function onBack() { app.stop(true); return false; }
}
