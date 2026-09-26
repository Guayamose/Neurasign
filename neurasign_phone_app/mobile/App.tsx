import { useEffect, useState, useSyncExternalStore } from 'react';
import { Alert, AppState, Linking, Pressable, ScrollView, StyleSheet, Text, TextInput, View, ActivityIndicator, Platform } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { LinkController, allowLocalHttp, type Preview } from './src/controller';
import type { EnrollmentLink } from '../src/enrollment';

const controller = new LinkController();
void controller.initialize();
export default function App() {
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot);
  const [permission, requestPermission] = useCameraPermissions();
  const [camera, setCamera] = useState(false), [link, setLink] = useState(''), [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<{ link: EnrollmentLink; preview: Preview } | null>(null);
  const [localError, setLocalError] = useState('');
  const [foreground, setForeground] = useState(AppState.currentState === 'active');
  async function act(fn: () => Promise<void>) { if (busy) return; setBusy(true); setLocalError(''); try { await fn(); } catch (e) { setLocalError(e instanceof Error ? e.message : 'Please retry.'); } finally { setBusy(false); } }
  async function openCode(value: string) { setCamera(false); await act(async () => { setPreview(await controller.preview(value)); setLink(''); }); }
  useEffect(() => {
    const handler = ({ url }: { url: string }) => { if (url.startsWith('neurasign://enroll') && !controller.state.enrollment && !controller.state.pending) void openCode(url); };
    const sub = Linking.addEventListener('url', handler);
    void Linking.getInitialURL().then(url => { if (url) handler({ url }); });
    const app = AppState.addEventListener('change', value => { setForeground(value === 'active'); if (value !== 'active') setCamera(false); });
    return () => { sub.remove(); app.remove(); };
  }, []);
  function button(title: string, action: () => void, secondary = false, disabled = false) {
    return <Pressable accessibilityRole="button" accessibilityLabel={title} disabled={busy || disabled} onPress={action} style={[styles.button, secondary && styles.secondary, (busy || disabled) && { opacity: 0.5 }]}><Text style={[styles.buttonText, secondary && { color: '#29452d' }]}>{title}</Text></Pressable>;
  }
  return <View style={styles.screen}><StatusBar style="dark" /><ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled"><View style={styles.header}><View style={styles.mark}><Text style={styles.markText}>N</Text></View><View><Text style={styles.brand}>NEURASIGN</Text><Text style={styles.eyebrow}>LINK YOUR WEARABLE</Text></View></View>
    {allowLocalHttp && <Text style={styles.dev}>DEVELOPMENT BUILD · LOCAL SERVER ENABLED</Text>}
    {!state.ready ? <View style={styles.card}><ActivityIndicator color="#537941" /><Text style={styles.body}>Opening secure storage…</Text></View> : preview ? <>
      <Text style={styles.title}>Your connection.</Text><Text style={styles.subtitle}>Check these details before sharing.</Text>
      <View style={styles.card}><Text style={styles.eyebrow}>COMPANY</Text><Text style={styles.company}>{preview.preview.company}</Text><View style={styles.divider} /><Text style={styles.eyebrow}>EMPLOYEE</Text><Text style={styles.company}>{preview.preview.employee}</Text><Text style={styles.body}>{preview.preview.team}</Text><Text style={styles.server}>{preview.link.apiOrigin}</Text></View>
      <Text style={styles.body}>Your wearable’s measurements will be visible to authorized company managers. You can pause at any time.</Text>
      {button('Confirm & connect', () => void act(async () => { const value = preview; setPreview(null); await controller.enroll(value.link); }))}
      {button('Cancel', () => setPreview(null), true)}
    </> : state.pending ? <><Text style={styles.title}>Finish connecting.</Text><Text style={styles.body}>The company may have received your confirmation. Retry to safely recover the same connection.</Text>{button('Retry connection', () => void act(() => controller.retryEnrollment()))}</> : !state.enrollment ? <>
      <Text style={styles.title}>One link.{"\n"}Your wearable.</Text><Text style={styles.subtitle}>Scan the connection code from your team’s NEURASIGN dashboard.</Text>
      <View style={styles.steps}><Text style={styles.step}>01  Scan your company code</Text><Text style={styles.step}>02  Connect your wearable</Text><Text style={styles.step}>03  Keep your phone nearby</Text></View>
      {camera && foreground && permission?.granted ? <View style={styles.camera}><CameraView style={{ flex: 1 }} facing="back" barcodeScannerSettings={{ barcodeTypes: ['qr'] }} onBarcodeScanned={busy ? undefined : ({ data }) => void openCode(data)} /><Text style={styles.cameraHint}>Point at the dashboard QR</Text></View> : button('Scan connection code', () => void act(async () => { const result = permission?.granted ? permission : await requestPermission(); if (!result.granted) throw new Error('Allow camera access or paste a connection link below.'); setCamera(true); }))}
      {camera && button('Close camera', () => setCamera(false), true)}
      <View style={styles.card}><Text style={styles.label}>Have a connection link?</Text><TextInput style={styles.input} accessibilityLabel="Connection link" placeholder="Paste your NEURASIGN link" autoCapitalize="none" autoCorrect={false} value={link} onChangeText={setLink} secureTextEntry multiline={false} />{button('Open connection link', () => void openCode(link), true, !link.trim())}</View>
    </> : <>
      <Text style={styles.title}>Your wearable link.</Text><View style={styles.card}><Text style={styles.eyebrow}>{state.enrollment.company.toUpperCase()}</Text><Text style={styles.company}>{state.enrollment.employee}</Text><View style={styles.divider} /><View style={styles.statusRow}><View style={[styles.dot, { backgroundColor: state.running && state.ble === 'connected' && !state.offline ? '#659344' : '#b4996d' }]} /><Text accessibilityLiveRegion="polite" style={styles.label}>{state.status}</Text></View><Text style={styles.body}>{state.enrollment.candidate?.name ?? 'No wearable connected'}</Text></View>
      <View style={styles.metrics}><View><Text style={styles.number}>{state.queued}</Text><Text style={styles.eyebrow}>WAITING TO SEND</Text></View><View><Text style={styles.smallNumber}>{state.lastSent ? new Date(state.lastSent).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</Text><Text style={styles.eyebrow}>LAST UPLOAD</Text></View></View>
      {state.enrollment.intent === 'disconnect' ? <Text style={styles.body}>Capture has stopped. Keep the app open with internet access to finish disconnecting.</Text> : state.running ? <>{button('Pause sharing', () => void act(() => controller.pause()))}<Text style={styles.body}>Keep the wearable near this phone. {Platform.OS === 'android' ? 'A notification stays visible while the connection is active.' : 'iOS controls background Bluetooth activity. Reopen the app if sending stops.'}</Text></> : <>
        {state.enrollment.candidate && button('Resume connection', () => void act(() => controller.start(state.enrollment!.candidate!)))}
        {button(state.scanning ? 'Searching…' : 'Find wearable', () => void act(() => controller.scan()), Boolean(state.enrollment.candidate), state.scanning)}
        <Text style={styles.body}>Put your wearable in heart-rate broadcast mode. Bluetooth Heart Rate devices appear here.</Text>
        {state.scanning && <ActivityIndicator color="#537941" />}
        {state.candidates.map(candidate => <View key={candidate.id} style={styles.card}><Text style={styles.label}>{candidate.name}</Text><Text style={styles.body}>Heart rate · Bluetooth</Text>{button(`Connect ${candidate.name}`, () => void act(() => controller.start(candidate)), true)}</View>)}
        {!state.scanning && !state.candidates.length && <Text style={styles.hint}>No sensor listed? Check Bluetooth and the wearable’s broadcast settings. Some devices require a manufacturer integration.</Text>}
        {!state.enrollment.paused && button('Pause sharing', () => void act(() => controller.pause()), true)}
      </>}
      <Pressable accessibilityRole="button" accessibilityLabel="Disconnect company" disabled={busy} onPress={() => Alert.alert('Disconnect this phone?', 'Measurement capture stops and phone access is revoked when the server is reachable.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Disconnect', style: 'destructive', onPress: () => void act(() => controller.disconnect()) }])}><Text style={styles.disconnect}>Disconnect company</Text></Pressable>
    </>}
    {busy && <ActivityIndicator style={{ marginTop: 12 }} color="#537941" />}
    {Boolean(localError || state.error) && <Text accessibilityRole="alert" style={styles.error}>{localError || state.error}</Text>}
    <Text style={styles.footer}>Wearable → Phone → Your company</Text>
  </ScrollView></View>;
}
const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#f3f5ef' }, content: { paddingHorizontal: 26, paddingTop: 64, paddingBottom: 40, maxWidth: 580, width: '100%', alignSelf: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 40 }, mark: { width: 44, height: 44, borderRadius: 14, backgroundColor: '#537941', alignItems: 'center', justifyContent: 'center' }, markText: { color: 'white', fontWeight: '800', fontSize: 26 }, brand: { fontSize: 21, color: '#233c2d', fontWeight: '800', letterSpacing: 1 }, eyebrow: { fontSize: 10, color: '#6d7d68', letterSpacing: 1.2, fontWeight: '600' },
  title: { fontSize: 37, fontWeight: '700', letterSpacing: -1.5, color: '#243d2c', marginBottom: 12, lineHeight: 43 }, subtitle: { fontSize: 16, lineHeight: 24, color: '#6a7965', marginBottom: 28 }, body: { fontSize: 14, lineHeight: 21, color: '#687560', marginVertical: 10 }, card: { backgroundColor: '#fff', borderWidth: 1, borderColor: '#e0e6d9', padding: 22, borderRadius: 22, marginVertical: 12 }, company: { fontSize: 23, fontWeight: '600', color: '#243d2c', marginTop: 8 }, divider: { height: 1, backgroundColor: '#e7ebdf', marginVertical: 20 },
  steps: { marginBottom: 20, gap: 14 }, step: { fontSize: 15, color: '#4f644a', fontWeight: '500' }, button: { backgroundColor: '#537941', borderRadius: 14, paddingVertical: 17, paddingHorizontal: 14, alignItems: 'center', marginVertical: 7 }, secondary: { backgroundColor: '#e9efdf', borderWidth: 1, borderColor: '#dce5d1' }, buttonText: { fontSize: 15, fontWeight: '700', color: '#fff' }, input: { borderWidth: 1, borderColor: '#dce5d1', borderRadius: 12, padding: 14, marginTop: 14, color: '#29452d' }, label: { fontSize: 16, fontWeight: '600', color: '#29452d', flexShrink: 1 }, statusRow: { flexDirection: 'row', gap: 10, alignItems: 'center' }, dot: { height: 10, width: 10, borderRadius: 5 }, metrics: { flexDirection: 'row', justifyContent: 'space-between', padding: 20, marginBottom: 16 }, number: { fontSize: 36, color: '#29452d', marginBottom: 7 }, smallNumber: { fontSize: 29, color: '#29452d', marginBottom: 14 }, hint: { fontSize: 12, lineHeight: 19, color: '#78836f', marginVertical: 14 }, error: { backgroundColor: '#f5e5dd', color: '#8c4831', padding: 15, borderRadius: 12, marginTop: 16, lineHeight: 20 }, footer: { fontSize: 11, textAlign: 'center', color: '#89937e', marginTop: 35 }, disconnect: { color: '#855b4c', textAlign: 'center', padding: 20, marginTop: 14 }, server: { fontSize: 12, color: '#748267', marginTop: 12 }, dev: { fontSize: 9, color: '#957649', marginTop: -25, marginBottom: 22 }, camera: { height: 300, borderRadius: 20, overflow: 'hidden' }, cameraHint: { position: 'absolute', bottom: 15, alignSelf: 'center', color: '#fff', backgroundColor: '#0008', padding: 10 },
});
