import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/auth/session_invalidation.dart';
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
  @override
  Future<AuthSession> build() async {
    ref.watch(sessionInvalidationProvider);

    try {
      final user = await ref.watch(authRepositoryProvider).restoreSession();

      if (user == null) {
        return const AuthSession.unauthenticated();
      }

      return AuthSession.authenticated(user);
    } on AuthFailure catch (failure) {
      return AuthSession.unauthenticated(failure: failure);
    } catch (_) {
      return AuthSession.unauthenticated(failure: AuthFailure.unexpected());
    }
  }

  Future<void> login({required String email, required String password}) async {
    final currentSession = state.asData?.value;

    if (currentSession?.isAuthenticated == true ||
        currentSession?.isLoginInProgress == true) {
      return;
    }

    state = const AsyncData(
      AuthSession.unauthenticated(isLoginInProgress: true),
    );

    try {
      final user = await ref
          .read(authRepositoryProvider)
          .login(email: email, password: password);

      state = AsyncData(AuthSession.authenticated(user));
    } on AuthFailure catch (failure) {
      state = AsyncData(AuthSession.unauthenticated(failure: failure));
    } catch (_) {
      state = AsyncData(
        AuthSession.unauthenticated(failure: AuthFailure.unexpected()),
      );
    }
  }

  Future<void> logout() async {
    try {
      await ref.read(authRepositoryProvider).logout();
    } finally {
      state = const AsyncData(AuthSession.unauthenticated());
    }
  }
}
