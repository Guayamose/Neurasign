package com.neurasign.garminlink

import android.os.Handler
import android.os.Looper
import com.garmin.android.connectiq.ConnectIQ
import com.garmin.android.connectiq.IQApp
import com.garmin.android.connectiq.IQDevice
import expo.modules.kotlin.Promise
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import org.json.JSONObject

/** Garmin Connect IQ public companion SDK; no Garmin Health enterprise binary. */
class GarminLinkModule : Module() {
  private val app = IQApp("bfa7bcf39bd4469c89082b8eca52f2fd")
  private var sdk: ConnectIQ? = null
  private var ready = false
  private var pending: Promise? = null
  private val handler = Handler(Looper.getMainLooper())
  private val timeout = Runnable { pending?.reject("GARMIN_TIMEOUT", "Open Garmin Connect and pair your watch, then retry.", null); pending = null }
  private val subscribed = mutableSetOf<Long>()
  private val devices = mutableMapOf<String, IQDevice>()
  private val context get() = requireNotNull(appContext.reactContext)
  private fun peers(promise: Promise) {
    try {
      devices.clear()
      for (device in sdk!!.connectedDevices.orEmpty()) devices[device.deviceIdentifier.toString()] = device
      promise.resolve(devices.map { (id, device) -> mapOf("id" to id, "name" to device.friendlyName) })
    } catch (e: Exception) { promise.reject("GARMIN_UNAVAILABLE", "Garmin Connect is unavailable or no watch is paired.", e) }
  }
  override fun definition() = ModuleDefinition {
    Name("GarminLink")
    Events("message")
    AsyncFunction("peers") { promise: Promise -> handler.post {
      if (ready) peers(promise)
      else if (pending != null) promise.reject("GARMIN_BUSY", "Garmin connection is initializing.", null)
      else {
        pending = promise; handler.postDelayed(timeout, 10000)
        try {
          if (sdk == null) sdk = ConnectIQ.getInstance(context, ConnectIQ.IQConnectType.WIRELESS)
          sdk!!.initialize(context, false, object : ConnectIQ.ConnectIQListener {
            override fun onSdkReady() { handler.post { ready = true; handler.removeCallbacks(timeout); pending?.let { peers(it) }; pending = null } }
            override fun onInitializeError(status: ConnectIQ.IQSdkErrorStatus) { handler.post { ready = false; handler.removeCallbacks(timeout); pending?.reject("GARMIN_UNAVAILABLE", "Install/open Garmin Connect and pair your watch.", null); pending = null } }
            override fun onSdkShutDown() { ready = false }
          })
        } catch (e: Exception) { handler.removeCallbacks(timeout); pending?.reject("GARMIN_UNAVAILABLE", "Garmin Connect could not initialize.", e); pending = null }
      }
    } }
    AsyncFunction("send") { node: String, message: String, promise: Promise -> handler.post {
      try {
        check(ready); val device = requireNotNull(devices[node]); require(message.length <= 10000)
        val objectValue = JSONObject(message)
        if (objectValue.optString("kind") == "start" && subscribed.add(device.deviceIdentifier)) sdk!!.registerForAppEvents(device, app) { sender, _, values, status ->
          if (status == ConnectIQ.IQMessageStatus.SUCCESS) for (value in values.orEmpty()) {
            if (value is Map<*, *>) {
              val json = JSONObject(value).toString()
              if (json.length <= 60000) sendEvent("message", mapOf("node" to sender.deviceIdentifier.toString(), "message" to json))
            }
          }
        }
        val payload = objectValue.keys().asSequence().associateWith { objectValue.get(it) }
        sdk!!.sendMessage(device, app, payload) { _, _, status ->
          if (status == ConnectIQ.IQMessageStatus.SUCCESS) promise.resolve(null)
          else promise.reject("GARMIN_SEND", "Open NEURASIGN Link on your Garmin watch and keep Garmin Connect running.", null)
        }
      } catch (e: Exception) { promise.reject("GARMIN_SEND", "Garmin watch connection is unavailable.", e) }
    } }
    OnStopObserving { handler.post { try { sdk?.unregisterAllForEvents() } catch (_: Exception) { }; subscribed.clear() } }
    OnDestroy { handler.post { handler.removeCallbacks(timeout); pending?.reject("GARMIN_CLOSED", "Garmin connection closed.", null); pending = null; try { sdk?.shutdown(context) } catch (_: Exception) { }; sdk = null; ready = false; subscribed.clear() } }
  }
}
