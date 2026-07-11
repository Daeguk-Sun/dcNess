package example.sms

data class Intent(val payload: String)

interface SmsIngress {
    fun receiveSms(intent: Intent)
}

class SmsReceiver(private val ingress: SmsIngress) {
    fun onReceive(intent: Intent) = ingress.receiveSms(intent)
}
