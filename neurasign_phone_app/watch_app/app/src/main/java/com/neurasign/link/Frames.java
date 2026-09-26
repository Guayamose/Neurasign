package com.neurasign.link;

import java.time.Instant;
import java.util.*;
import org.json.*;

/** Lossless per-channel blocks; no inference, uniform-rate assumption or averaging. */
final class Frames {
  record Point(long time, double value) {}
  record Channel(String metric, String unit) {}
  private final Map<String, Map<Channel, ArrayList<Point>>> pending = new LinkedHashMap<>();
  void add(String source, String metric, String unit, long time, double value) {
    if (!Double.isFinite(value) || time < 946684800000L) throw new IllegalArgumentException("Invalid watch sample or clock");
    var points = pending.computeIfAbsent(source, k -> new LinkedHashMap<>()).computeIfAbsent(new Channel(metric, unit), k -> new ArrayList<>());
    if (points.size() >= 8192) throw new IllegalStateException("Watch capture buffer is full");
    points.add(new Point(time, value));
  }
  List<JSONObject> drain() throws JSONException {
    var output = new ArrayList<JSONObject>();
    for (var source : pending.entrySet()) {
      var groups = new ArrayList<JSONArray>();
      for (var entry : source.getValue().entrySet()) {
        var points = entry.getValue(); points.sort(Comparator.comparingLong(Point::time));
        int start = 0, group = 0;
        while (start < points.size()) {
          int end = start + 1;
          while (end < points.size() && end - start < 512 && points.get(end).time - points.get(start).time <= 10000) end++;
          Point last = points.get(end - 1);
          JSONArray samples = new JSONArray(), offsets = new JSONArray();
          for (int i = start; i < end; i++) { samples.put(points.get(i).value); offsets.put(points.get(i).time - last.time); }
          var row = new JSONObject().put("metric", entry.getKey().metric).put("unit", entry.getKey().unit)
            .put("measured_at", Instant.ofEpochMilli(last.time).toString()).put("value", last.value)
            .put("samples", samples).put("sample_offsets_ms", offsets);
          if (groups.size() <= group) groups.add(new JSONArray());
          groups.get(group++).put(row); start = end;
        }
      }
      for (JSONArray group : groups) output.add(new JSONObject().put("source", source.getKey()).put("measurements", group));
    }
    pending.clear(); return output;
  }
  void clear() { pending.clear(); }
  static JSONObject capability(String metric, String unit, String method) throws JSONException {
    return new JSONObject().put("metric", metric).put("unit", unit).put("method", method)
      .put("delivery_mode", "stream").put("measurement_kind", "sample").put("timestamp_basis", "device");
  }
}
