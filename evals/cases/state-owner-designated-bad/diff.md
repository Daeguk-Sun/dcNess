```diff
diff --git a/feature/room/topbar/LeaveRoomViewModel.kt b/feature/room/topbar/LeaveRoomViewModel.kt
new file mode 100644
--- /dev/null
+++ b/feature/room/topbar/LeaveRoomViewModel.kt
@@
+package app.feature.room.topbar
+
+data class LeaveRoomUiState(
+    val dialogVisible: Boolean = false,
+    val isLeaving: Boolean = false,
+    val error: String? = null,
+)
+
+@HiltViewModel
+class LeaveRoomViewModel @Inject constructor(
+    private val roomRepository: RoomRepository,
+    savedStateHandle: SavedStateHandle,
+) : ViewModel() {
+    private val roomId: String = checkNotNull(savedStateHandle["roomId"])
+    private val _uiState = MutableStateFlow(LeaveRoomUiState())
+    val uiState: StateFlow<LeaveRoomUiState> = _uiState.asStateFlow()
+    private val _events = Channel<RoomTopBarEvent>(Channel.BUFFERED)
+    val events = _events.receiveAsFlow()
+
+    fun open() = _uiState.update { it.copy(dialogVisible = true) }
+
+    fun dismiss() = _uiState.update { it.copy(dialogVisible = false, error = null) }
+
+    fun confirm() {
+        viewModelScope.launch {
+            _uiState.update { it.copy(isLeaving = true, error = null) }
+            roomRepository.leaveRoom(roomId)
+                .onSuccess {
+                    _uiState.update { it.copy(isLeaving = false, dialogVisible = false) }
+                    _events.send(RoomTopBarEvent.NavigateToRoomList)
+                }
+                .onFailure { e ->
+                    _uiState.update { it.copy(isLeaving = false, error = e.message) }
+                }
+        }
+    }
+}
diff --git a/feature/room/topbar/RoomTopBar.kt b/feature/room/topbar/RoomTopBar.kt
--- a/feature/room/topbar/RoomTopBar.kt
+++ b/feature/room/topbar/RoomTopBar.kt
@@
 @Composable
 fun RoomTopBar(
     viewModel: RoomTopBarViewModel = hiltViewModel(),
+    leaveViewModel: LeaveRoomViewModel = hiltViewModel(),
     onNavigateToRoomList: () -> Unit,
 ) {
     val state by viewModel.uiState.collectAsStateWithLifecycle()
+    val leaveState by leaveViewModel.uiState.collectAsStateWithLifecycle()
+    LaunchedEffect(Unit) {
+        leaveViewModel.events.collect { event ->
+            if (event is RoomTopBarEvent.NavigateToRoomList) onNavigateToRoomList()
+        }
+    }
     TopAppBar(
         title = { Text(state.title) },
         actions = {
             RoomMenu(
                 muted = state.muted,
                 onToggleMute = viewModel::onToggleMute,
+                onLeave = leaveViewModel::open,
             )
         },
     )
+    if (leaveState.dialogVisible) {
+        LeaveRoomDialog(
+            isLeaving = leaveState.isLeaving,
+            error = leaveState.error,
+            onConfirm = leaveViewModel::confirm,
+            onDismiss = leaveViewModel::dismiss,
+        )
+    }
 }
diff --git a/data/room/RoomRepository.kt b/data/room/RoomRepository.kt
--- a/data/room/RoomRepository.kt
+++ b/data/room/RoomRepository.kt
@@
 interface RoomRepository {
     suspend fun setMuted(roomId: String, muted: Boolean): Result<Unit>
+    suspend fun leaveRoom(roomId: String): Result<Unit>
 }
diff --git a/feature/room/topbar/LeaveRoomViewModelTest.kt b/feature/room/topbar/LeaveRoomViewModelTest.kt
new file mode 100644
--- /dev/null
+++ b/feature/room/topbar/LeaveRoomViewModelTest.kt
@@
+class LeaveRoomViewModelTest {
+    @Test fun open_showsDialog() = runTest {
+        val vm = LeaveRoomViewModel(FakeRoomRepository(), SavedStateHandle(mapOf("roomId" to "r1")))
+        vm.open()
+        assertTrue(vm.uiState.value.dialogVisible)
+    }
+
+    @Test fun confirm_success_navigatesToRoomList() = runTest {
+        val vm = LeaveRoomViewModel(FakeRoomRepository(), SavedStateHandle(mapOf("roomId" to "r1")))
+        vm.confirm()
+        assertEquals(RoomTopBarEvent.NavigateToRoomList, vm.events.first())
+    }
+
+    @Test fun confirm_failure_keepsScreenAndShowsError() = runTest {
+        val vm = LeaveRoomViewModel(FakeRoomRepository(fail = true), SavedStateHandle(mapOf("roomId" to "r1")))
+        vm.confirm()
+        advanceUntilIdle()
+        assertNotNull(vm.uiState.value.error)
+    }
+}
```
