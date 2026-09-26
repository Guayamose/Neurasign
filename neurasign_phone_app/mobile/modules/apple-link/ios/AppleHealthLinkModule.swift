import ExpoModulesCore
import HealthKit

// Read-only wearable records. Anchors are committed by JS only after encrypted storage.
public class AppleHealthLinkModule: Module {
  private let health = HKHealthStore()
  private let definitions: [(String, String, HKUnit, String)] = [
    ("heart_rate", HKQuantityTypeIdentifier.heartRate.rawValue, HKUnit.count().unitDivided(by: .minute()), "bpm"),
    ("hrv_sdnn", HKQuantityTypeIdentifier.heartRateVariabilitySDNN.rawValue, .secondUnit(with: .milli), "ms"),
    ("oxygen_saturation", HKQuantityTypeIdentifier.oxygenSaturation.rawValue, .percent(), "%"),
    ("respiratory_rate", HKQuantityTypeIdentifier.respiratoryRate.rawValue, HKUnit.count().unitDivided(by: .minute()), "breaths/min"),
    ("body_temperature", HKQuantityTypeIdentifier.bodyTemperature.rawValue, .degreeCelsius(), "°C"),
    ("skin_temperature", "HKQuantityTypeIdentifierAppleSleepingWristTemperature", .degreeCelsius(), "°C"),
    ("steps", HKQuantityTypeIdentifier.stepCount.rawValue, .count(), "count")
  ]
  private func sampleType(_ metric: String) -> HKSampleType? {
    if metric == "skin_temperature" { if #available(iOS 16.0, *) {} else { return nil } }
    if metric == "electrocardiogram" { return HKObjectType.electrocardiogramType() }
    guard let definition = definitions.first(where: { $0.0 == metric }) else { return nil }
    return HKObjectType.quantityType(forIdentifier: HKQuantityTypeIdentifier(rawValue: definition.1))
  }
  public func definition() -> ModuleDefinition {
    Name("AppleHealthLink")
    AsyncFunction("authorize") { (promise: Promise) in
      guard HKHealthStore.isHealthDataAvailable() else { promise.reject("HEALTH_UNAVAILABLE", "Apple Health is unavailable on this device."); return }
      let types = Set(self.definitions.compactMap { self.sampleType($0.0) } + [HKObjectType.electrocardiogramType()])
      self.health.requestAuthorization(toShare: [], read: Set(types.map { $0 as HKObjectType })) { ok, error in
        if let error = error { promise.reject("HEALTH_PERMISSION", error.localizedDescription) }
        else { promise.resolve(ok) } // Apple intentionally does not reveal read permission status.
      }
    }
    AsyncFunction("page") { (metric: String, encoded: String?, since: Double, promise: Promise) in
      guard let type = self.sampleType(metric), since.isFinite else { promise.reject("HEALTH_TYPE", "Health metric unavailable."); return }
      var anchor: HKQueryAnchor? = nil
      if let encoded = encoded {
        guard let data = Data(base64Encoded: encoded), let decoded = try? NSKeyedUnarchiver.unarchivedObject(ofClass: HKQueryAnchor.self, from: data) else {
          promise.reject("HEALTH_CURSOR", "Invalid Apple Health cursor."); return
        }
        anchor = decoded
      }
      let predicate = HKQuery.predicateForSamples(withStart: Date(timeIntervalSince1970: since), end: nil, options: .strictStartDate)
      let query = HKAnchoredObjectQuery(type: type, predicate: predicate, anchor: anchor, limit: metric == "electrocardiogram" ? 2 : 256) { _, samples, deleted, next, error in
        if let error = error { promise.reject("HEALTH_QUERY", error.localizedDescription); return }
        guard let next = next, let data = try? NSKeyedArchiver.archivedData(withRootObject: next, requiringSecureCoding: true) else { promise.reject("HEALTH_CURSOR", "Could not save Apple Health cursor."); return }
        let records = (samples ?? []).filter { sample in
          // Reject manual entries and records without wearable hardware provenance.
          if (sample.metadata?[HKMetadataKeyWasUserEntered] as? Bool) == true { return false }
          let model = (sample.device?.model ?? sample.sourceRevision.productType ?? "").lowercased()
          return ["watch", "band", "ring", "strap"].contains(where: { model.contains($0) })
        }
        if metric == "electrocardiogram" {
          self.ecgs(records.compactMap { $0 as? HKElectrocardiogram }, at: 0, rows: []) { rows, failure in
            if let failure = failure { promise.reject("HEALTH_ECG", failure.localizedDescription) }
            else { promise.resolve(["records": rows, "anchor": data.base64EncodedString(), "deleted": deleted?.count ?? 0]) }
          }
        } else {
          promise.resolve(["records": records.compactMap { self.quantity($0, metric) }, "anchor": data.base64EncodedString(), "deleted": deleted?.count ?? 0])
        }
      }
      self.health.execute(query)
    }
  }
  private func record(_ sample: HKSample, metric: String, unit: String, value: Double, time: Date, period: Int? = nil, suffix: String = "") -> [String: Any] {
    let manufacturer = sample.device?.manufacturer ?? "HealthKit wearable"
    let model = sample.device?.model ?? sample.sourceRevision.productType ?? "Wearable"
    let kind = period == nil ? "sample" : "summary"
    let formatter = ISO8601DateFormatter(); formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    var row: [String: Any] = ["metric": metric, "unit": unit, "value": value, "measured_at": formatter.string(from: time), "source_record_id": sample.uuid.uuidString + suffix]
    if let period = period { row["interval_seconds"] = period }
    return ["identity": "\(sample.sourceRevision.source.bundleIdentifier):\(manufacturer):\(model):\(sample.device?.localIdentifier ?? ""):\(kind)",
            "name": "\(model) · Apple Health", "manufacturer": manufacturer, "model": model, "kind": kind, "measurement": row]
  }
  private func quantity(_ sample: HKSample, _ metric: String) -> [String: Any]? {
    guard let sample = sample as? HKQuantitySample, let definition = definitions.first(where: { $0.0 == metric }) else { return nil }
    let duration = sample.endDate.timeIntervalSince(sample.startDate)
    if duration < 0 || duration > 604800 || ((metric == "hrv_sdnn" || metric == "steps") && duration <= 0) { return nil }
    let value = sample.quantity.doubleValue(for: definition.2) * (metric == "oxygen_saturation" ? 100 : 1)
    guard value.isFinite, !(metric == "heart_rate" && value <= 0) else { return nil }
    return record(sample, metric: metric, unit: definition.3, value: value, time: sample.endDate, period: duration > 0 ? Int(ceil(duration)) : nil)
  }
  private func ecgs(_ samples: [HKElectrocardiogram], at index: Int, rows: [[String: Any]], done: @escaping ([[String: Any]], Error?) -> Void) {
    if index >= samples.count { done(rows, nil); return }
    let sample = samples[index]
    var values: [Double] = [], times: [Double] = []
    let query = HKElectrocardiogramQuery(sample) { _, result in
      switch result {
      case .measurement(let measurement):
        if let voltage = measurement.quantity(for: .appleWatchSimilarToLeadI) {
          values.append(voltage.doubleValue(for: .voltUnit(with: .milli))); times.append(measurement.timeSinceSampleStart)
        }
      case .done:
        var output = rows
        var start = 0
        while start < values.count {
          var end = start
          while end+1 < values.count && end-start+1 < 512 && times[end+1]-times[start] <= 10 { end += 1 }
          var row = self.record(sample, metric: "electrocardiogram", unit: "mV", value: values[end], time: sample.startDate.addingTimeInterval(times[end]), suffix: ":\(start)")
          var measurement = row["measurement"] as! [String: Any]
          measurement["samples"] = Array(values[start...end]); measurement["sample_offsets_ms"] = times[start...end].map { ($0-times[end])*1000 }
          row["measurement"] = measurement; output.append(row); start = end+1
        }
        self.ecgs(samples, at: index+1, rows: output, done: done)
      case .error(let error): done([], error)
      @unknown default: done([], NSError(domain: "HealthKit", code: 1))
      }
    }
    health.execute(query)
  }
}
