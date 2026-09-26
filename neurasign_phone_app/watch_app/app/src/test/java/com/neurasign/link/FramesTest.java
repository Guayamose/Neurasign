package com.neurasign.link;

import org.junit.Test;
import static org.junit.Assert.*;

public class FramesTest {
  @Test public void preservesIrregularSamplesAcrossSizeAndDurationBoundaries() throws Exception {
    var frames = new Frames(); long start = 1790400000000L;
    for (int i = 0; i < 1100; i++) frames.add("source", "electrocardiogram", "mV", start + i * 2L, (i - 550) / 1000.0);
    for (int i = 0; i < 4; i++) frames.add("source", "electrodermal_conductance", "µS", start + i * 7000L, i / 10.0);
    var groups = frames.drain(); int ecg = 0, eda = 0;
    for (var group : groups) {
      var rows = group.getJSONArray("measurements");
      for (int i = 0; i < rows.length(); i++) {
        var row = rows.getJSONObject(i); var samples = row.getJSONArray("samples"); var offsets = row.getJSONArray("sample_offsets_ms");
        assertTrue(samples.length() <= 512); assertTrue(offsets.getLong(0) >= -10000); assertEquals(0, offsets.getLong(offsets.length()-1));
        assertEquals(samples.getDouble(samples.length()-1), row.getDouble("value"), 0);
        if (row.getString("metric").equals("electrocardiogram")) {
          for (int n = 0; n < samples.length(); n++) assertEquals((ecg++ - 550) / 1000.0, samples.getDouble(n), 0);
        } else eda += samples.length();
      }
    }
    assertEquals(1100, ecg); assertEquals(4, eda); assertTrue(frames.drain().isEmpty());
  }
  @Test public void rejectsInvalidClockOrValuesAndClearsStoppedSessions() throws Exception {
    var frames = new Frames();
    assertThrows(IllegalArgumentException.class, () -> frames.add("source", "heart_rate", "bpm", 0, 70));
    assertThrows(IllegalArgumentException.class, () -> frames.add("source", "heart_rate", "bpm", 1790400000000L, Double.NaN));
    frames.add("source", "heart_rate", "bpm", 1790400000000L, 70); frames.clear(); assertTrue(frames.drain().isEmpty());
  }
}
