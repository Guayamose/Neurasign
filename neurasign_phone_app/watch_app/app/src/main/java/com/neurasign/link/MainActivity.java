package com.neurasign.link;

import android.app.Activity;
import android.os.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.widget.*;
import android.view.Gravity;
import java.util.ArrayList;

/** Connection controls only. Team analytics belong to the company dashboard. */
public final class MainActivity extends Activity {
  private final Handler handler = new Handler();
  private TextView state;
  private final Runnable refresh = new Runnable() { public void run() { state.setText(SensorService.status); handler.postDelayed(this, 1000); } };
  @Override public void onCreate(Bundle saved) {
    super.onCreate(saved);
    var scroll = new ScrollView(this); var column = new LinearLayout(this); column.setOrientation(LinearLayout.VERTICAL); column.setGravity(Gravity.CENTER); column.setPadding(24, 36, 24, 36); scroll.addView(column);
    var title = new TextView(this); title.setText("NEURASIGN LINK"); title.setTextSize(18); title.setGravity(Gravity.CENTER); column.addView(title);
    state = new TextView(this); state.setGravity(Gravity.CENTER); state.setPadding(0, 16, 0, 16); column.addView(state);
    button(column, "Start", this::permissions);
    button(column, "Stop", () -> stopService(new Intent(this, SensorService.class)));
    button(column, "ECG · touch electrode", () -> demand("ECG_ON_DEMAND"));
    button(column, "Measure oxygen", () -> demand("SPO2_ON_DEMAND"));
    var note = new TextView(this); note.setText("Connect this watch in NEURASIGN on your Android phone. Sharing stops if the phone connection expires."); note.setTextSize(11); note.setGravity(Gravity.CENTER); column.addView(note);
    setContentView(scroll);
  }
  private void button(LinearLayout parent, String text, Runnable action) { var b = new Button(this); b.setText(text); b.setOnClickListener(v -> action.run()); parent.addView(b); }
  private void permissions() {
    String[] requested = {"android.permission.BODY_SENSORS", "android.permission.ACTIVITY_RECOGNITION", "android.permission.POST_NOTIFICATIONS", "com.samsung.android.hardware.sensormanager.permission.READ_ADDITIONAL_HEALTH_DATA"};
    var missing = new ArrayList<String>();
    for (String permission : requested) {
      if (permission.endsWith("POST_NOTIFICATIONS") && Build.VERSION.SDK_INT < 33) continue;
      if (permission.startsWith("com.samsung") && !Build.MANUFACTURER.equalsIgnoreCase("samsung")) continue;
      if (checkSelfPermission(permission) != PackageManager.PERMISSION_GRANTED) missing.add(permission);
    }
    if (missing.isEmpty()) arm(); else requestPermissions(missing.toArray(new String[0]), 1);
  }
  @Override public void onRequestPermissionsResult(int request, String[] permissions, int[] results) { super.onRequestPermissionsResult(request, permissions, results); if (request == 1) arm(); }
  private void arm() {
    if (checkSelfPermission("android.permission.BODY_SENSORS") != PackageManager.PERMISSION_GRANTED && checkSelfPermission("android.permission.ACTIVITY_RECOGNITION") != PackageManager.PERMISSION_GRANTED) { SensorService.status = "Allow sensor or activity access to start."; return; }
    try { startForegroundService(new Intent(this, SensorService.class)); }
    catch (RuntimeException e) { SensorService.status = "Open the app and allow sensor access to start."; }
  }
  private void demand(String type) { if (SensorService.running) startService(new Intent(this, SensorService.class).setAction(type)); else SensorService.status = "Start and connect your phone first."; }
  @Override public void onResume() { super.onResume(); handler.post(refresh); }
  @Override public void onPause() { handler.removeCallbacks(refresh); super.onPause(); }
}
