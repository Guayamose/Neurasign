const { withAndroidManifest } = require('expo/config-plugins');
module.exports = config => withAndroidManifest(config, mod => {
  const manifest = mod.modResults.manifest;
  const application = manifest.application[0];
  application.$['android:allowBackup'] = 'false';
  application.$['android:usesCleartextTraffic'] = config.extra?.allowLocalHttp ? 'true' : 'false';
  application.service = application.service || [];
  application.service = application.service.filter(service => service.$['android:name'] !== 'com.asterinet.react.bgactions.RNBackgroundActionsTask');
  application.service.push({ $: { 'android:name': 'com.asterinet.react.bgactions.RNBackgroundActionsTask', 'android:foregroundServiceType': 'connectedDevice', 'android:exported': 'false' } });
  return mod;
});
