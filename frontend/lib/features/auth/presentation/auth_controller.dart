import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/auth/session_invalidation.dart';
import '../../../core/storage/secure_storage_provider.dart';
import '../data/auth_repository.dart';
import '../domain/auth_failure.dart';
import '../domain/auth_user.dart';

final authControllerProvider =
    AsyncNotifierProvider<AuthController, AuthSession>(AuthController.new);

class AuthSession {
  const AuthSession._({
    required this.user,
    required this.isLoginInProgress,
    required this.failure,
  });

  const AuthSession.authenticated(AuthUser user)
    : this._(user: user, isLoginInProgress: false, failure: null);

  const AuthSession.unauthenticated({
    bool isLoginInProgress = false,
    AuthFailure? failure,
  }) : this._(
         user: null,
         isLoginInProgress: isLoginInProgress,
         failure: failure,
       );

  final AuthUser? user;
  final bool isLoginInProgress;
  final AuthFailure? failure;

  bool get isAuthenticated => user != null;
}

class AuthController extends AsyncNotifier<AuthSession> {
  int _operation = 0;

  bool _canPublish(int operation) => ref.mounted && operation == _operation;

  AuthSession _currentSession() => ref.mounted
      ? state.asData?.value ?? const AuthSession.unauthenticated()
      : const AuthSession.unauthenticated();

  @override
  Future<AuthSession> build() async {
    ref.watch(sessionInvalidationProvider);
    final operation = ++_operation;
    ref.onDispose(() => _operation++);
    try {
      final user = await ref.watch(authRepositoryProvider).restoreSession();
      if (!_canPublish(operation)) return _currentSession();
      return user == null
          ? const AuthSession.unauthenticated()
          : AuthSession.authenticated(user);
    } on SessionSuperseded {
      return _currentSession();
    } on AuthFailure catch (failure) {
      if (!_canPublish(operation)) return _currentSession();
      return AuthSession.unauthenticated(failure: failure);
    } catch (_) {
      if (!_canPublish(operation)) return _currentSession();
      return AuthSession.unauthenticated(failure: AuthFailure.unexpected());
    }
  }

  Future<void> login({required String email, required String password}) async {
    final currentSession = state.asData?.value;
    if (currentSession?.isAuthenticated == true ||
        currentSession?.isLoginInProgress == true) {
      return;
    }

    final operation = ++_operation;
    state = const AsyncData(
      AuthSession.unauthenticated(isLoginInProgress: true),
    );
    try {
      final user = await ref
          .read(authRepositoryProvider)
          .login(email: email, password: password);
      if (_canPublish(operation)) {
        state = AsyncData(AuthSession.authenticated(user));
      }
    } on SessionSuperseded {
      // A newer lifecycle operation owns state publication.
    } on AuthFailure catch (failure) {
      if (_canPublish(operation)) {
        state = AsyncData(AuthSession.unauthenticated(failure: failure));
      }
    } catch (_) {
      if (_canPublish(operation)) {
        state = AsyncData(
          AuthSession.unauthenticated(failure: AuthFailure.unexpected()),
        );
      }
    }
  }

  Future<AuthUser?> reloadCurrentUser() async {
    if (state.asData?.value.isAuthenticated != true) return null;
    final operation = ++_operation;
    try {
      final user = await ref.read(authRepositoryProvider).getCurrentUser();
      if (!_canPublish(operation)) return null;
      state = AsyncData(AuthSession.authenticated(user));
      return user;
    } on SessionSuperseded {
      return null;
    } catch (_) {
      if (!_canPublish(operation)) return null;
      rethrow;
    }
  }

  Future<void> logout() async {
    ++_operation;
    // Publish local logout immediately. A delayed remote revoke owns no state.
    final logout = ref.read(authRepositoryProvider).logout();
    state = const AsyncData(AuthSession.unauthenticated());
    await logout;
  }
}
