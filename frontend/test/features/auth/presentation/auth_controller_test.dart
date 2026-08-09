import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/features/auth/data/auth_repository.dart';
import 'package:mealio/features/auth/domain/auth_failure.dart';
import 'package:mealio/features/auth/domain/auth_user.dart';
import 'package:mealio/features/auth/presentation/auth_controller.dart';

import '../../../helpers/auth_test_fakes.dart';

void main() {
  ProviderContainer createContainer(FakeAuthRepository repository) {
    final container = ProviderContainer(
      overrides: [authRepositoryProvider.overrideWithValue(repository)],
    );
    addTearDown(container.dispose);
    return container;
  }

  test('initial state is loading while session restore is unresolved', () {
    final completer = Completer<AuthUser?>();
    final repository = FakeAuthRepository(
      restoreHandler: () => completer.future,
    );
    final container = createContainer(repository);

    final subscription = container.listen(
      authControllerProvider,
      (previous, next) {},
      fireImmediately: true,
    );
    addTearDown(subscription.close);

    expect(
      container.read(authControllerProvider),
      isA<AsyncLoading<AuthSession>>(),
    );
  });

  test('restore without token becomes unauthenticated', () async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);
    final container = createContainer(repository);

    await container.read(authControllerProvider.future);

    final session = container.read(authControllerProvider).asData!.value;
    expect(session.isAuthenticated, isFalse);
    expect(session.failure, isNull);
  });

  test('restore valid session becomes authenticated', () async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
    );
    final container = createContainer(repository);

    await container.read(authControllerProvider.future);

    final session = container.read(authControllerProvider).asData!.value;
    expect(session.user, testAuthUser);
    expect(session.isAuthenticated, isTrue);
  });

  test('login success becomes authenticated', () async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      loginHandler: ({required email, required password}) async => testAuthUser,
    );
    final container = createContainer(repository);

    await container.read(authControllerProvider.future);
    await container
        .read(authControllerProvider.notifier)
        .login(email: 'pavel@example.com', password: 'test-password');

    final session = container.read(authControllerProvider).asData!.value;
    expect(session.user, testAuthUser);
    expect(repository.loginCalls, 1);
  });

  test('login error remains unauthenticated with safe failure', () async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      loginHandler: ({required email, required password}) {
        throw AuthFailure.invalidCredentials();
      },
    );
    final container = createContainer(repository);

    await container.read(authControllerProvider.future);
    await container
        .read(authControllerProvider.notifier)
        .login(email: 'pavel@example.com', password: 'wrong-password');

    final session = container.read(authControllerProvider).asData!.value;
    expect(session.isAuthenticated, isFalse);
    expect(session.failure?.type, AuthFailureType.invalidCredentials);
  });

  test('logout becomes unauthenticated', () async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
    );
    final container = createContainer(repository);

    await container.read(authControllerProvider.future);
    await container.read(authControllerProvider.notifier).logout();

    final session = container.read(authControllerProvider).asData!.value;
    expect(session.isAuthenticated, isFalse);
    expect(repository.logoutCalls, 1);
  });
}
