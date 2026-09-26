import SwiftUI
import WatchConnectivity
import CoreMotion
import HealthKit
import WatchKit

@main struct NeurasignWatchApp: App {
  @StateObject private var link = WatchLink()
  @Environment(\.scenePhase) private var phase
  var body: some Scene {
    WindowGroup {
      VStack(spacing: 12) {
        Text("NEURASIGN").font(.headline)
        Text(link.status).font(.caption).multilineTextAlignment(.center)
        Button(link.enabled ? "Stop sharing" : "Start") { link.enabled ? link.stop() : link.arm() }
        Text("Keep this app visible. HR follows watch availability.").font(.footnote).foregroundStyle(.secondary)
      }.padding().onChange(of: phase) { _, value in link.foreground = value == .active; if value != .active { link.stop() } }
    }
  }
}
final class WatchLink: NSObject, ObservableObject, WCSessionDelegate {
  @Published var status = "Start here, then connect on your phone."
  @Published var enabled = false
  var foreground = true
  private let health = HKHealthStore(), motion = CMMotionManager()
  private var query: HKQuery?, timer: Timer?, sessionID: String?, lease = Date.distantPast
  private var pending: [Int: [String: Any]] = [:], sequence = 0
  private var channels: [String: [(Double, Date)]] = [:]
  private let deviceID: String = {
    let key = "neurasign-watch-installation"
    if let existing = UserDefaults.standard.string(forKey: key) { return existing }
    let id = UUID().uuidString; UserDefaults.standard.set(id, forKey: key); return id
  }()
  private let boot = Date().addingTimeInterval(-ProcessInfo.processInfo.systemUptime)
  private let formatter: ISO8601DateFormatter = { let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]; return f }()
  override init() { super.init(); WCSession.default.delegate = self; WCSession.default.activate() }
  func arm() {
    health.requestAuthorization(toShare: [], read: [HKObjectType.quantityType(forIdentifier: .heartRate)!]) { _, _ in
      DispatchQueue.main.async { self.enabled = true; self.status = "Ready. Connect from your phone." }
    }
  }
  func stop() {
    motion.stopAccelerometerUpdates(); motion.stopGyroUpdates(); motion.stopMagnetometerUpdates()
    if let query = query { health.stop(query) }; query = nil
    timer?.invalidate(); timer = nil; channels.removeAll(); pending.removeAll(); sessionID = nil
    enabled = false; status = "Sharing stopped."
  }
  private func send(_ message: [String: Any]) {
    guard WCSession.default.isReachable, let data = try? JSONSerialization.data(withJSONObject: message, options: [.sortedKeys]), let payload = String(data: data, encoding: .utf8) else { return }
    WCSession.default.sendMessage(["payload": payload], replyHandler: nil, errorHandler: { _ in })
  }
  private func envelope(_ kind: String) -> [String: Any] { ["version": 1, "kind": kind, "session": sessionID ?? ""] }
  private func begin(_ id: String) {
    guard enabled && foreground else { return }
    if sessionID == id { return }
    stop(); enabled = true; sessionID = id; lease = Date(); sequence = 0
    var metrics = ["heart_rate": "bpm"]
    for (available, prefix, unit) in [(motion.isAccelerometerAvailable, "acceleration", "m/s²"), (motion.isGyroAvailable, "angular_velocity", "°/s"), (motion.isMagnetometerAvailable, "magnetic_field", "gauss")] where available {
      for axis in ["x", "y", "z"] { metrics[prefix+"_"+axis] = unit }
    }
    var hello = envelope("hello")
    hello["device_id"] = deviceID; hello["manufacturer"] = "Apple"; hello["model"] = WKInterfaceDevice.current().model
    hello["sources"] = [["id": "apple-watch-sensors", "name": "Watch sensors", "capabilities": metrics.sorted(by: { $0.key < $1.key }).map { metric, unit in
      ["metric": metric, "unit": unit, "measurement_kind": "sample", "delivery_mode": "stream", "timestamp_basis": "device", "method": metric == "heart_rate" ? "healthkit-fresh-watch-sample" : "coremotion-device-time"]
    }]]
    hello["warnings"] = ["Foreground collection only. Heart rate is delivered when watchOS records a sample; continuous HR is not guaranteed."]
    send(hello); status = "Sharing with linked phone."
    let start = Date()
    let type = HKObjectType.quantityType(forIdentifier: .heartRate)!
    let handler: (HKAnchoredObjectQuery, [HKSample]?, [HKDeletedObject]?, HKQueryAnchor?, Error?) -> Void = { [weak self] _, samples, _, _, _ in
      DispatchQueue.main.async {
        guard let self = self, self.sessionID == id else { return }
        for case let sample as HKQuantitySample in samples ?? [] where sample.startDate >= start && sample.startDate == sample.endDate && sample.device?.manufacturer == "Apple" {
          self.channels["heart_rate", default: []].append((sample.quantity.doubleValue(for: HKUnit.count().unitDivided(by: .minute())), sample.endDate))
        }
      }
    }
    let q = HKAnchoredObjectQuery(type: type, predicate: HKQuery.predicateForSamples(withStart: start, end: nil), anchor: nil, limit: 256, resultsHandler: handler)
    q.updateHandler = handler; query = q; health.execute(q)
    motion.accelerometerUpdateInterval = 0.04; motion.gyroUpdateInterval = 0.04; motion.magnetometerUpdateInterval = 0.04
    if motion.isAccelerometerAvailable { motion.startAccelerometerUpdates(to: .main) { [weak self] data, _ in if let d = data { self?.axes("acceleration", [d.acceleration.x, d.acceleration.y, d.acceleration.z], d.timestamp, 9.80665) } } }
    if motion.isGyroAvailable { motion.startGyroUpdates(to: .main) { [weak self] data, _ in if let d = data { self?.axes("angular_velocity", [d.rotationRate.x, d.rotationRate.y, d.rotationRate.z], d.timestamp, 180 / Double.pi) } } }
    if motion.isMagnetometerAvailable { motion.startMagnetometerUpdates(to: .main) { [weak self] data, _ in if let d = data { self?.axes("magnetic_field", [d.magneticField.x, d.magneticField.y, d.magneticField.z], d.timestamp, 0.01) } } }
    timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.tick(metrics) }
  }
  private func axes(_ prefix: String, _ values: [Double], _ timestamp: Double, _ factor: Double) {
    guard sessionID != nil else { return }
    for (i, axis) in ["x", "y", "z"].enumerated() { channels[prefix+"_"+axis, default: []].append((values[i]*factor, boot.addingTimeInterval(timestamp))) }
  }
  private func tick(_ units: [String: String]) {
    guard Date().timeIntervalSince(lease) < 30, pending.count < 16 else { stop(); status = "Phone disconnected. Reconnect to share."; return }
    var rows: [[String: Any]] = []
    for metric in channels.keys.sorted() {
      let values = (channels.removeValue(forKey: metric) ?? []).sorted { $0.1 < $1.1 }
      guard let last = values.last else { continue }
      if values.count > 512 || last.1.timeIntervalSince(values[0].1) > 10 { stop(); status = "Sensor buffer full. Reconnect."; return }
      rows.append(["metric": metric, "unit": units[metric]!, "value": last.0, "measured_at": formatter.string(from: last.1), "samples": values.map { $0.0 }, "sample_offsets_ms": values.map { $0.1.timeIntervalSince(last.1)*1000 }])
    }
    if !rows.isEmpty { var frame = envelope("samples"); frame["source"] = "apple-watch-sensors"; frame["sequence"] = sequence; frame["measurements"] = rows; pending[sequence] = frame; sequence += 1; send(frame) }
    // Retries preserve the exact sequence, values and times until the phone persists them.
    if let oldest = pending.keys.min(), let frame = pending[oldest] { send(frame) }
  }
  func session(_ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: Error?) {}
  func session(_ session: WCSession, didReceiveMessage message: [String: Any], replyHandler: @escaping ([String: Any]) -> Void) {
    replyHandler(["received": true])
    guard let payload = message["payload"] as? String, payload.utf8.count <= 10000, let data = payload.data(using: .utf8), let body = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any], body["version"] as? Int == 1, let id = body["session"] as? String, id.count <= 80 else { return }
    DispatchQueue.main.async {
      if body["kind"] as? String == "start" { self.begin(id); return }
      guard id == self.sessionID else { return }
      switch body["kind"] as? String {
      case "stop": self.stop()
      case "lease": self.lease = Date(); self.send(self.envelope("heartbeat"))
      case "ack": if let sequence = body["sequence"] as? Int { self.pending.removeValue(forKey: sequence) }
      default: break
      }
    }
  }
}
