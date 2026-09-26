import ExpoModulesCore
import WatchConnectivity

private final class PhoneWatchBridge: NSObject, WCSessionDelegate {
  var received: ((String) -> Void)?
  var activated: (() -> Void)?
  func session(_ session: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) { activated?() }
  func sessionDidBecomeInactive(_ session: WCSession) {}
  func sessionDidDeactivate(_ session: WCSession) { session.activate() }
  func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
    if let payload = message["payload"] as? String, payload.utf8.count <= 100000 { received?(payload) }
  }
}
public class AppleWatchLinkModule: Module {
  private let bridge = PhoneWatchBridge()
  public func definition() -> ModuleDefinition {
    Name("AppleWatchLink")
    Events("message")
    OnCreate {
      guard WCSession.isSupported() else { return }
      self.bridge.received = { [weak self] payload in self?.sendEvent("message", ["node": "apple-watch", "message": payload]) }
      WCSession.default.delegate = self.bridge; WCSession.default.activate()
    }
    AsyncFunction("peers") { () -> [[String: String]] in
      guard WCSession.isSupported(), WCSession.default.activationState == .activated,
            WCSession.default.isPaired, WCSession.default.isWatchAppInstalled else { return [] }
      return [["id": "apple-watch", "name": "Apple Watch · NEURASIGN Link"]]
    }
    AsyncFunction("send") { (node: String, message: String, promise: Promise) in
      guard node == "apple-watch", message.utf8.count <= 10000, WCSession.default.isReachable else {
        promise.reject("WATCH_UNREACHABLE", "Open NEURASIGN Link on Apple Watch and keep both apps visible."); return
      }
      WCSession.default.sendMessage(["payload": message], replyHandler: { _ in promise.resolve(nil) }, errorHandler: { error in promise.reject("WATCH_SEND", error.localizedDescription) })
    }
    OnDestroy { self.bridge.received = nil }
  }
}
