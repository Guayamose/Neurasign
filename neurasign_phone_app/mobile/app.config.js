module.exports = {
  expo: {
    name: 'NEURASIGN Link', slug: 'neurasign-link', version: '0.1.0', scheme: 'neurasign',
    orientation: 'portrait', userInterfaceStyle: 'light',
    icon: './assets/icon.png',
    splash: { image: './assets/splash-icon.png', resizeMode: 'contain', backgroundColor: '#edf2e9' },
    ios: { bundleIdentifier: 'com.neurasign.link', entitlements: { 'com.apple.developer.healthkit': true }, supportsTablet: false, infoPlist: { NSHealthShareUsageDescription: 'Read measurements recorded by your wearable and share them with your authorized company managers while sharing is enabled.', UIBackgroundModes: ['bluetooth-central'], NSBluetoothAlwaysUsageDescription: 'Connect your wearable and send its measurements to your company.' } },
    android: { package: 'com.neurasign.link', permissions: ['android.permission.FOREGROUND_SERVICE', 'android.permission.FOREGROUND_SERVICE_CONNECTED_DEVICE', 'android.permission.POST_NOTIFICATIONS'], blockedPermissions: ['android.permission.RECORD_AUDIO'], adaptiveIcon: { foregroundImage: './assets/icon.png', backgroundColor: '#edf2e9' } },
    plugins: [
      ['expo-camera', { cameraPermission: 'Scan your company’s connection code.', recordAudioAndroid: false }],
      ['expo-secure-store', { configureAndroidBackup: true }],
      ['expo-sqlite', { useSQLCipher: true }],
      ['react-native-ble-plx', { isBackgroundEnabled: true, modes: ['central'], bluetoothAlwaysPermission: 'Connect your wearable and share its measurements with your company.', neverForLocation: true }],
      './plugins/withGateway',
    ],
    extra: { allowLocalHttp: process.env.LOCAL_GATEWAY_HTTP === '1' },
  },
};
