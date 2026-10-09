import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/auth/session_invalidation.dart';
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

  test('reload current user replaces authenticated user', () async {
    final verifiedUser = AuthUser(
      id: testAuthUser.id,
      email: testAuthUser.email,
      fullName: testAuthUser.fullName,
      emailVerified: true,
      createdAt: testAuthUser.createdAt,
      updatedAt: testAuthUser.updatedAt,
    );
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
      currentUserHandler: () async => verifiedUser,
    );
    final container = createContainer(repository);

    await container.read(authControllerProvider.future);
    final user = await container
        .read(authControllerProvider.notifier)
        .reloadCurrentUser();

    expect(user, verifiedUser);
    expect(repository.currentUserCalls, 1);
    expect(
      container.read(authControllerProvider).asData!.value.user,
      verifiedUser,
    );
  });

  test(
    'reload current user is a no-op without authenticated session',
    () async {
      final repository = FakeAuthRepository(restoreHandler: () async => null);
      final container = createContainer(repository);

      await container.read(authControllerProvider.future);
      final user = await container
          .read(authControllerProvider.notifier)
          .reloadCurrentUser();

      expect(user, isNull);
      expect(repository.currentUserCalls, 0);
    },
  );

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

  test(
    'global session invalidation rebuilds into unauthenticated state',
    () async {
      final repository = FakeAuthRepository(
        restoreHandler: () async => testAuthUser,
      );
      final container = createContainer(repository);

      await container.read(authControllerProvider.future);
      expect(
        container.read(authControllerProvider).asData!.value.isAuthenticated,
        isTrue,
      );

      repository.restoreHandler = () async => null;
      final invalidated = Completer<void>();
      final subscription = container.listen(authControllerProvider, (
        previous,
        next,
      ) {
        final session = next.asData?.value;
        if (session != null &&
            !session.isAuthenticated &&
            !invalidated.isCompleted) {
          invalidated.complete();
        }
      });
      addTearDown(subscription.close);

      container.read(sessionInvalidationProvider.notifier).invalidate();
      await invalidated.future;

      final session = container.read(authControllerProvider).asData!.value;
      expect(session.isAuthenticated, isFalse);
      expect(repository.restoreCalls, 2);
    },
  );

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

  test('logout failure still leaves controller unauthenticated', () async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
      logoutHandler: () async {
        throw AuthFailure.unexpected();
      },
    );
    final container = createContainer(repository);

    await container.read(authControllerProvider.future);

    await expectLater(
      container.read(authControllerProvider.notifier).logout(),
      throwsA(isA<AuthFailure>()),
    );

    final session = container.read(authControllerProvider).asData!.value;
    expect(session.isAuthenticated, isFalse);
    expect(repository.logoutCalls, 1);
  });

  for (final fails in [false, true]) {
    test(
      'late login ${fails ? 'failure' : 'success'} after logout/relogin cannot publish',
      () async {
        final oldLogin = Completer<AuthUser>();
        addTearDown(() {
          if (!oldLogin.isCompleted) oldLogin.complete(testAuthUser);
        });
        final repository = FakeAuthRepository(
          restoreHandler: () async => null,
          loginHandler: ({required email, required password}) =>
              oldLogin.future,
        );
        final container = createContainer(repository);
        await container.read(authControllerProvider.future);
        final controller = container.read(authControllerProvider.notifier);
        final old = controller.login(
          email: 'a@example.com',
          password: 'synthetic',
        );
        await controller.logout();
        repository.loginHandler = ({required email, required password}) async =>
            testAuthUser;
        await controller.login(email: 'a@example.com', password: 'synthetic');
        if (fails) {
          oldLogin.completeError(AuthFailure.invalidCredentials());
        } else {
          oldLogin.complete(
            AuthUser(
              id: testAuthUser.id,
              email: testAuthUser.email,
              fullName: 'Stale profile from previous login',
              createdAt: testAuthUser.createdAt,
              updatedAt: testAuthUser.updatedAt,
            ),
          );
        }
        await old;
        final session = container.read(authControllerProvider).asData!.value;
        expect(session.user, testAuthUser);
        expect(session.failure, isNull);
      },
    );
  }

  for (final relogin in [false, true]) {
    test(
      'late restore cannot overwrite ${relogin ? 'new login' : 'logout'}',
      () async {
        final restored = Completer<AuthUser?>();
        addTearDown(() {
          if (!restored.isCompleted) restored.complete(null);
        });
        final repository = FakeAuthRepository(
          restoreHandler: () => restored.future,
          loginHandler: ({required email, required password}) async =>
              testAuthUser,
        );
        final container = createContainer(repository);
        final initial = container.read(authControllerProvider.future);
        final controller = container.read(authControllerProvider.notifier);
        await controller.logout();
        if (relogin) {
          await controller.login(email: 'a@example.com', password: 'synthetic');
        }
        // A different old user makes an accidental stale publication observable.
        restored.complete(
          AuthUser(
            id: 'old-id',
            email: 'old@example.com',
            fullName: null,
            createdAt: testAuthUser.createdAt,
            updatedAt: testAuthUser.updatedAt,
          ),
        );
        await initial;
        await container.pump();
        expect(
          container.read(authControllerProvider).asData!.value.user,
          relogin ? testAuthUser : isNull,
        );
      },
    );
  }

  for (final fails in [false, true]) {
    test(
      'late reload ${fails ? 'failure' : 'success'} does not resurrect logged-out session',
      () async {
        final reloaded = Completer<AuthUser>();
        addTearDown(() {
          if (!reloaded.isCompleted) reloaded.complete(testAuthUser);
        });
        final repository = FakeAuthRepository(
          restoreHandler: () async => testAuthUser,
          currentUserHandler: () => reloaded.future,
        );
        final container = createContainer(repository);
        await container.read(authControllerProvider.future);
        final controller = container.read(authControllerProvider.notifier);
        final old = controller.reloadCurrentUser();
        await controller.logout();
        if (fails) {
          reloaded.completeError(AuthFailure.invalidSession());
        } else {
          reloaded.complete(testAuthUser);
        }
        expect(await old, isNull);
        expect(
          container.read(authControllerProvider).asData!.value.user,
          isNull,
        );
      },
    );
  }

  test('delayed logout completion does not clear new login', () async {
    final revoked = Completer<void>();
    addTearDown(() {
      if (!revoked.isCompleted) revoked.complete();
    });
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
      logoutHandler: () => revoked.future,
      loginHandler: ({required email, required password}) async => testAuthUser,
    );
    final container = createContainer(repository);
    await container.read(authControllerProvider.future);
    final controller = container.read(authControllerProvider.notifier);
    final old = controller.logout();
    expect(container.read(authControllerProvider).asData!.value.user, isNull);
    await controller.login(email: 'a@example.com', password: 'synthetic');
    revoked.complete();
    await old;
    expect(
      container.read(authControllerProvider).asData!.value.user,
      testAuthUser,
    );
  });

  for (final operation in ['login', 'reload', 'logout']) {
    test(
      '$operation completion after dispose performs no state access',
      () async {
        final done = Completer<AuthUser>();
        addTearDown(() {
          if (!done.isCompleted) done.complete(testAuthUser);
        });
        final repository = FakeAuthRepository(
          restoreHandler: () async =>
              operation == 'login' ? null : testAuthUser,
          loginHandler: ({required email, required password}) => done.future,
          currentUserHandler: () => done.future,
          logoutHandler: () async {
            await done.future;
          },
        );
        final container = ProviderContainer(
          overrides: [authRepositoryProvider.overrideWithValue(repository)],
        );
        await container.read(authControllerProvider.future);
        final controller = container.read(authControllerProvider.notifier);
        final pending = switch (operation) {
          'login' => controller.login(
            email: 'a@example.com',
            password: 'synthetic',
          ),
          'reload' => controller.reloadCurrentUser(),
          _ => controller.logout(),
        };
        container.dispose();
        done.complete(testAuthUser);
        await pending;
      },
    );
  }
}
