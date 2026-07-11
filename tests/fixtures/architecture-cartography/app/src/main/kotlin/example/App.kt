package example

import example.data.MessageObserver

class App(private val messageObserver: MessageObserver) {
    fun onCreate() {
        messageObserver.start()
    }
}
