# Apple Watch and HealthKit

Two separate routes:

- **Apple Health on iPhone:** reads supported wearable records already stored in HealthKit, including interval HRV, oxygen, temperature and recorded ECG. No watch companion is needed for this route. Read permissions and manufacturer synchronization still apply.
- **NEURASIGN Link on Apple Watch:** foreground sensor companion using CoreMotion and WatchConnectivity. It streams available motion channels and fresh instantaneous HealthKit HR samples when watchOS supplies them. No fake workout, continuous-HR promise, raw PPG or EDA claim.

Both routes use the phone's existing company enrollment, queue and authenticated server contract. The watch does not receive company credentials.

## macOS build

Requires Xcode with iOS/watchOS SDKs, signing team/capabilities, Node 22 and XcodeGen. No Apple build has been run in this Linux workspace.

1. In `../mobile`, run `npm ci`, `npx expo prebuild --platform ios` and `npx expo run:ios --device`. Use the same Apple development team and enable the generated HealthKit entitlement. Native iOS is generated; do not edit generated files for persistent changes.
2. In this directory run `xcodegen generate`, then open `NeurasignWatch.xcodeproj`. Select the signing team and a paired watch. The watch bundle `com.neurasign.link.watchapp` declares the iPhone companion `com.neurasign.link`; retain that association.
3. Build/run the watch target through Xcode onto the paired watch with the iPhone application installed. This separate development target is not an App Store archive; distribution needs embedding the watch target in the phone's release build and signing it.
4. Open both apps. On the watch tap **Start**, then use **Find wearable** on iPhone. A watch is listed only after WatchConnectivity activates and confirms the companion is installed; retry discovery if activation is still pending.

Compile-only check on macOS:

```bash
xcodegen generate
xcodebuild -project NeurasignWatch.xcodeproj -scheme NeurasignWatch \
  -sdk watchsimulator -destination 'generic/platform=watchOS Simulator' \
  -derivedDataPath build CODE_SIGNING_ALLOWED=NO build
```

The watch stops when its scene becomes inactive or its phone lease expires. Empty HR is expected when no fresh instantaneous sample is available; longer HR measurement intervals are imported through the HealthKit sync route. Motion timestamps retain CoreMotion monotonic timing mapped to watch wall time. Device availability, Health permissions, background policy, battery and throughput require real Apple validation.

HealthKit import excludes manual records and sources without recognizable wearable hardware provenance. This is deliberately conservative and may exclude third-party records whose manufacturer omitted device metadata. HealthKit changes are read with anchors and stable record IDs; already uploaded records are not automatically deleted when a source record is removed in Health.
