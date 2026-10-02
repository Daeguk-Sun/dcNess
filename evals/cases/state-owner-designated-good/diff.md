```diff
diff --git a/feature/room/topbar/RoomTopBarUiState.kt b/feature/room/topbar/RoomTopBarUiState.kt
--- a/feature/room/topbar/RoomTopBarUiState.kt
+++ b/feature/room/topbar/RoomTopBarUiState.kt
@@
 data class RoomTopBarUiState(
     val title: String = "",
     val muted: Boolean = false,
+    val leaveDialogVisible: Boolean = false,
+    val isLeaving: Boolean = false,
+    val leaveError: String? = null,
 )
diff --git a/feature/room/topbar/RoomTopBarViewModel.kt b/feature/room/topbar/RoomTopBarViewModel.kt
--- a/feature/room/topbar/RoomTopBarViewModel.kt
+++ b/feature/room/topbar/RoomTopBarViewModel.kt
@@
     fun onToggleMute() {
         viewModelScope.launch {
             val next = !_uiState.value.muted
             roomRepository.setMuted(roomId, next)
                 .onSuccess { _uiState.update { it.copy(muted = next) } }
         }
     }
+
+    fun onLeaveClick() = _uiState.update { it.copy(leaveDialogVisible = true) }
+
+    fun onLeaveDismiss() = _uiState.update { it.copy(leaveDialogVisible = false, leaveError = null) }
+
+    fun onLeaveConfirm() {
+        viewModelScope.launch {
+            _uiState.update { it.copy(isLeaving = true, leaveError = null) }
+            roomRepository.leaveRoom(roomId)
+                .onSuccess {
+                    _uiState.update { it.copy(isLeaving = false, leaveDialogVisible = false) }
+                    _events.send(RoomTopBarEvent.NavigateToRoomList)
+                }
+                .onFailure { e ->
+                    _uiState.update { it.copy(isLeaving = false, leaveError = e.message) }
+                }
+        }
+    }
 }
diff --git a/feature/room/topbar/RoomTopBar.kt b/feature/room/topbar/RoomTopBar.kt
--- a/feature/room/topbar/RoomTopBar.kt
+++ b/feature/room/topbar/RoomTopBar.kt
@@
     TopAppBar(
         title = { Text(state.title) },
         actions = {
             RoomMenu(
                 muted = state.muted,
                 onToggleMute = viewModel::onToggleMute,
+                onLeave = viewModel::onLeaveClick,
             )
         },
     )
+    if (state.leaveDialogVisible) {
+        LeaveRoomDialog(
+            isLeaving = state.isLeaving,
+            error = state.leaveError,
+            onConfirm = viewModel::onLeaveConfirm,
+            onDismiss = viewModel::onLeaveDismiss,
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
diff --git a/feature/room/topbar/RoomTopBarViewModelTest.kt b/feature/room/topbar/RoomTopBarViewModelTest.kt
--- a/feature/room/topbar/RoomTopBarViewModelTest.kt
+++ b/feature/room/topbar/RoomTopBarViewModelTest.kt
@@
+    @Test fun leaveClick_showsDialog() = runTest {
+        val vm = viewModel()
+        vm.onLeaveClick()
+        assertTrue(vm.uiState.value.leaveDialogVisible)
+    }
+
+    @Test fun leaveConfirm_success_navigatesToRoomList() = runTest {
+        val vm = viewModel()
+        vm.onLeaveConfirm()
+        assertEquals(RoomTopBarEvent.NavigateToRoomList, vm.events.first())
+    }
+
+    @Test fun leaveConfirm_failure_keepsScreenAndShowsError() = runTest {
+        val vm = viewModel(repository = FakeRoomRepository(failLeave = true))
+        vm.onLeaveConfirm()
+        advanceUntilIdle()
+        assertNotNull(vm.uiState.value.leaveError)
+    }
```
