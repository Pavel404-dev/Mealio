import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mealio/app/app.dart';
import 'package:mealio/features/auth/data/auth_repository.dart';
import 'package:mealio/features/auth/domain/auth_failure.dart';
import 'package:mealio/features/auth/domain/auth_user.dart';
import 'package:mealio/features/auth/presentation/auth_controller.dart';

import '../../../helpers/auth_test_fakes.dart';

void main() {
  void useLargeTestSurface(WidgetTester tester) {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  Widget createApp(FakeAuthRepository repository) {
    return ProviderScope(
      overrides: [authRepositoryProvider.overrideWithValue(repository)],
      child: const MealioApp(),
    );
  }

  Future<void> openLoggedOutVerification(
    WidgetTester tester,
    FakeAuthRepository repository, {
    String? email,
    String? token,
  }) async {
    useLargeTestSurface(tester);
    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    final context = tester.element(find.byKey(const Key('login-screen')));
    final location = token == null
        ? '/verify-email'
        : '/verify-email?token=${Uri.encodeQueryComponent(token)}';

    GoRouter.of(context).go(location, extra: email);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('verify-email-screen')), findsOneWidget);
  }

  AuthUser verifiedUser() {
    return AuthUser(
      id: testAuthUser.id,
      email: testAuthUser.email,
      fullName: testAuthUser.fullName,
      emailVerified: true,
      createdAt: testAuthUser.createdAt,
      updatedAt: testAuthUser.updatedAt,
    );
  }

  testWidgets(
    'post-registration state displays email without automatic resend',
    (tester) async {
      final repository = FakeAuthRepository(restoreHandler: () async => null);

      await openLoggedOutVerification(
        tester,
        repository,
        email: 'registered@example.com',
      );

      expect(find.text('registered@example.com'), findsOneWidget);
      expect(
        find.byKey(const Key('verify-email-resend-button')),
        findsOneWidget,
      );
      expect(repository.requestEmailVerificationCalls, 0);
    },
  );

  testWidgets('resend loading prevents duplicate requests and is generic', (
    tester,
  ) async {
    final resendCompleter = Completer<void>();
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      requestEmailVerificationHandler: ({required email}) =>
          resendCompleter.future,
    );

    await openLoggedOutVerification(
      tester,
      repository,
      email: 'registered@example.com',
    );

    await tester.tap(find.byKey(const Key('verify-email-resend-button')));
    await tester.tap(find.byKey(const Key('verify-email-resend-button')));
    await tester.pump();

    expect(repository.requestEmailVerificationCalls, 1);
    expect(repository.lastVerificationRequestEmail, 'registered@example.com');
    expect(
      find.byKey(const Key('verify-email-resend-loading')),
      findsOneWidget,
    );

    resendCompleter.complete();
    await tester.pumpAndSettle();

    expect(
      find.text('If verification is needed, instructions have been sent.'),
      findsOneWidget,
    );
  });

  testWidgets('resend network failure shows safe error', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      requestEmailVerificationHandler: ({required email}) {
        throw AuthFailure.connection();
      },
    );

    await openLoggedOutVerification(
      tester,
      repository,
      email: 'registered@example.com',
    );

    await tester.tap(find.byKey(const Key('verify-email-resend-button')));
    await tester.pumpAndSettle();

    expect(
      find.text('Unable to connect to the server. Please try again.'),
      findsOneWidget,
    );
  });

  testWidgets('missing token and email shows safe unavailable state', (
    tester,
  ) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoggedOutVerification(tester, repository);

    expect(find.text('Verification link unavailable'), findsOneWidget);
    expect(repository.confirmEmailVerificationCalls, 0);
  });

  testWidgets('empty token is rejected before repository confirmation', (
    tester,
  ) async {
    useLargeTestSurface(tester);
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    final context = tester.element(find.byKey(const Key('login-screen')));
    GoRouter.of(context).go('/verify-email?token=');
    await tester.pumpAndSettle();

    expect(find.text('Verification link unavailable'), findsOneWidget);
    expect(repository.confirmEmailVerificationCalls, 0);
  });

  testWidgets(
    'logged-out token confirmation succeeds without rendering token',
    (tester) async {
      const token = 'opaque-token-never-render-me';
      final repository = FakeAuthRepository(restoreHandler: () async => null);

      await openLoggedOutVerification(tester, repository, token: token);

      expect(repository.confirmEmailVerificationCalls, 1);
      expect(repository.lastVerificationToken, token);
      expect(find.text('Email verified'), findsOneWidget);
      expect(find.textContaining(token), findsNothing);
      expect(
        find.byKey(const Key('verify-email-success-continue-button')),
        findsOneWidget,
      );
    },
  );

  testWidgets('generic invalid token state does not render raw token', (
    tester,
  ) async {
    const token = 'expired-secret-token';
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      confirmEmailVerificationHandler: ({required token}) {
        throw AuthFailure.invalidEmailVerification();
      },
    );

    await openLoggedOutVerification(tester, repository, token: token);

    expect(
      find.text('This verification link is invalid or has expired.'),
      findsOneWidget,
    );
    expect(find.textContaining(token), findsNothing);
  });

  testWidgets('confirmation network error is safe and retryable', (
    tester,
  ) async {
    const token = 'network-secret-token';
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      confirmEmailVerificationHandler: ({required token}) {
        throw AuthFailure.connection();
      },
    );

    await openLoggedOutVerification(tester, repository, token: token);

    expect(
      find.text('Unable to connect to the server. Please try again.'),
      findsOneWidget,
    );
    expect(
      find.byKey(const Key('verify-email-confirm-retry-button')),
      findsOneWidget,
    );
    expect(find.textContaining(token), findsNothing);
  });

  testWidgets('logged-in confirmation reloads current user from backend', (
    tester,
  ) async {
    useLargeTestSurface(tester);
    final updatedUser = verifiedUser();
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
      currentUserHandler: () async => updatedUser,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    final homeContext = tester.element(find.byKey(const Key('home-screen')));
    GoRouter.of(homeContext).go('/verify-email?token=logged-in-token');
    await tester.pumpAndSettle();

    expect(repository.confirmEmailVerificationCalls, 1);
    expect(repository.currentUserCalls, 1);
    expect(find.text('Email verified'), findsOneWidget);

    final screenContext = tester.element(
      find.byKey(const Key('verify-email-screen')),
    );
    final container = ProviderScope.containerOf(screenContext);
    expect(
      container.read(authControllerProvider).asData?.value.user?.emailVerified,
      isTrue,
    );
  });

  testWidgets(
    'sync retry reloads account without reconfirming consumed token',
    (tester) async {
      useLargeTestSurface(tester);
      const token = 'single-use-verification-token';
      final repository = FakeAuthRepository(
        restoreHandler: () async => testAuthUser,
        currentUserHandler: () async {
          throw AuthFailure.connection();
        },
      );

      await tester.pumpWidget(createApp(repository));
      await tester.pumpAndSettle();

      final context = tester.element(find.byKey(const Key('home-screen')));
      GoRouter.of(
        context,
      ).go('/verify-email?token=${Uri.encodeQueryComponent(token)}');
      await tester.pumpAndSettle();

      expect(repository.confirmEmailVerificationCalls, 1);
      expect(repository.currentUserCalls, 1);
      expect(
        find.byKey(const Key('verify-email-sync-retry-button')),
        findsOneWidget,
      );

      repository.currentUserHandler = () async => verifiedUser();

      await tester.tap(find.byKey(const Key('verify-email-sync-retry-button')));
      await tester.pumpAndSettle();

      expect(repository.confirmEmailVerificationCalls, 1);
      expect(repository.currentUserCalls, 2);
      expect(find.text('Email verified'), findsOneWidget);
    },
  );

  testWidgets('already verified authenticated user is not offered resend', (
    tester,
  ) async {
    useLargeTestSurface(tester);
    final repository = FakeAuthRepository(
      restoreHandler: () async => verifiedUser(),
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    final context = tester.element(find.byKey(const Key('home-screen')));
    GoRouter.of(context).go('/verify-email');
    await tester.pumpAndSettle();

    expect(find.text('Email verified'), findsOneWidget);
    expect(find.byKey(const Key('verify-email-resend-button')), findsNothing);
  });

  testWidgets('already verified authenticated user skips token confirmation', (
    tester,
  ) async {
    useLargeTestSurface(tester);
    const token = 'already-verified-token';
    final repository = FakeAuthRepository(
      restoreHandler: () async => verifiedUser(),
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    final context = tester.element(find.byKey(const Key('home-screen')));
    GoRouter.of(
      context,
    ).go('/verify-email?token=${Uri.encodeQueryComponent(token)}');
    await tester.pumpAndSettle();

    expect(find.text('Email verified'), findsOneWidget);
    expect(repository.confirmEmailVerificationCalls, 0);
    expect(find.textContaining(token), findsNothing);
  });

  testWidgets('authenticated pending user can refresh verification status', (
    tester,
  ) async {
    useLargeTestSurface(tester);
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
      currentUserHandler: () async => verifiedUser(),
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    final context = tester.element(find.byKey(const Key('home-screen')));
    GoRouter.of(context).go('/verify-email');
    await tester.pumpAndSettle();

    expect(
      find.byKey(const Key('verify-email-refresh-button')),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const Key('verify-email-refresh-button')));
    await tester.pumpAndSettle();

    expect(repository.currentUserCalls, 1);
    expect(find.text('Email verified'), findsOneWidget);
  });

  testWidgets('verification waits for unresolved cold-start auth restore', (
    tester,
  ) async {
    useLargeTestSurface(tester);
    final restoreCompleter = Completer<AuthUser?>();
    final repository = FakeAuthRepository(
      restoreHandler: () => restoreCompleter.future,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pump();

    expect(find.byKey(const Key('splash-screen')), findsOneWidget);

    final context = tester.element(find.byKey(const Key('splash-screen')));
    GoRouter.of(context).go('/verify-email?token=cold-start-token');
    await tester.pump();
    await tester.pump();

    expect(find.byKey(const Key('verify-email-screen')), findsOneWidget);
    expect(
      find.byKey(const Key('verify-email-confirm-loading')),
      findsOneWidget,
    );
    expect(repository.confirmEmailVerificationCalls, 0);

    restoreCompleter.complete(null);
    await tester.pumpAndSettle();

    expect(repository.confirmEmailVerificationCalls, 1);
    expect(find.text('Email verified'), findsOneWidget);
    expect(find.byKey(const Key('verify-email-screen')), findsOneWidget);
    expect(find.byKey(const Key('login-screen')), findsNothing);
  });

  testWidgets('cold-start verified session skips consumed token confirmation', (
    tester,
  ) async {
    useLargeTestSurface(tester);
    const token = 'already-consumed-token';
    final restoreCompleter = Completer<AuthUser?>();
    final repository = FakeAuthRepository(
      restoreHandler: () => restoreCompleter.future,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pump();

    final context = tester.element(find.byKey(const Key('splash-screen')));
    GoRouter.of(
      context,
    ).go('/verify-email?token=${Uri.encodeQueryComponent(token)}');
    await tester.pump();
    await tester.pump();

    expect(repository.confirmEmailVerificationCalls, 0);

    restoreCompleter.complete(verifiedUser());
    await tester.pumpAndSettle();

    expect(repository.confirmEmailVerificationCalls, 0);
    expect(find.text('Email verified'), findsOneWidget);
    expect(find.textContaining(token), findsNothing);
  });
}
