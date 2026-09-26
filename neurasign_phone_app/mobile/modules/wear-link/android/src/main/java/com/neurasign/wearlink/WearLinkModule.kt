package com.neurasign.wearlink

import com.google.android.gms.tasks.Tasks
import com.google.android.gms.wearable.MessageClient
import com.google.android.gms.wearable.Wearable
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import java.util.concurrent.TimeUnit

class WearLinkModule : Module() {
  private val context get() = requireNotNull(appContext.reactContext)
  private val listener = MessageClient.OnMessageReceivedListener { event ->
    if (event.path == "/neurasign/link/v1" && event.data.size <= 100000) {
      sendEvent("message", mapOf("node" to event.sourceNodeId, "message" to String(event.data, Charsets.UTF_8)))
    }
  }
  override fun definition() = ModuleDefinition {
    Name("WearLink")
    Events("message")
    OnStartObserving { Wearable.getMessageClient(context).addListener(listener) }
    OnStopObserving { Wearable.getMessageClient(context).removeListener(listener) }
    AsyncFunction("peers") {
      Tasks.await(Wearable.getNodeClient(context).connectedNodes, 8, TimeUnit.SECONDS)
        .filter { it.isNearby }.map { mapOf("id" to it.id, "name" to it.displayName) }
    }
    AsyncFunction("send") { node: String, message: String ->
      require(message.toByteArray(Charsets.UTF_8).size <= 100000)
      val peers = Tasks.await(Wearable.getNodeClient(context).connectedNodes, 8, TimeUnit.SECONDS)
      require(peers.any { it.id == node && it.isNearby }) { "Keep the paired watch near this phone." }
      Tasks.await(Wearable.getMessageClient(context).sendMessage(node, "/neurasign/link/v1", message.toByteArray(Charsets.UTF_8)), 8, TimeUnit.SECONDS)
    }
  }
}
