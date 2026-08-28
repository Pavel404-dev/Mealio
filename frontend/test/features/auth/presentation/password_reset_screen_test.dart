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

  Future<void> openLoggedOutReset(
    WidgetTester tester,
    FakeAuthRepository repository, {
    String? token,
  }) async {
    useLargeTestSurface(tester);
    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    final context = tester.element(find.byKey(const Key('login-screen')));
    final location = token == null
        ? '/reset-password'
        : '/reset-password?token=${Uri.encodeQueryComponent(token)}';
    GoRouter.of(context).go(location);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('reset-password-screen')), findsOneWidget);
  }

  Future<void> enterValidPassword(WidgetTester tester, String password) async {
    await tester.enterText(
      find.byKey(const Key('reset-password-field')),
      password,
    );
    await tester.enterText(
      find.byKey(const Key('reset-password-confirm-field')),
      password,
    );
  }

  testWidgets('login opens forgot-password flow', (tester) async {
    useLargeTestSurface(tester);
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('forgot-password-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('forgot-password-screen')), findsOneWidget);
  });

  testWidgets('forgot-password validates email before request', (tester) async {
    useLargeTestSurface(tester);
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();
    final context = tester.element(find.byKey(const Key('login-screen')));
    GoRouter.of(context).go('/forgot-password');
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const Key('forgot-password-email-field')),
      'invalid-email',
    );
    await tester.tap(find.byKey(const Key('forgot-password-submit-button')));
    await tester.pump();

    expect(find.text('Enter a valid email address.'), findsOneWidget);
    expect(repository.requestPasswordResetOtpCalls, 0);
  });

  testWidgets('forgot-password requests OTP and navigates duplicate-safe', (
    tester,
  ) async {
    useLargeTestSurface(tester);
    final completer = Completer<void>();
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      requestPasswordResetOtpHandler: ({required email}) => completer.future,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();
    final context = tester.element(find.byKey(const Key('login-screen')));
    GoRouter.of(context).go('/forgot-password');
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const Key('forgot-password-email-field')),
      '  PAVEL@EXAMPLE.COM  ',
    );
    await tester.tap(find.byKey(const Key('forgot-password-submit-button')));
    await tester.tap(find.byKey(const Key('forgot-password-submit-button')));
    await tester.pump();

    expect(repository.requestPasswordResetOtpCalls, 1);
    expect(repository.lastPasswordResetOtpRequestEmail, 'pavel@example.com');
    expect(
      find.byKey(const Key('forgot-password-loading-indicator')),
      findsOneWidget,
    );

    completer.complete();
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('password-reset-otp-screen')), findsOneWidget);
    expect(find.text('pavel@example.com'), findsOneWidget);
  });

  testWidgets('forgot-password network failure is safe', (tester) async {
    useLargeTestSurface(tester);
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      requestPasswordResetOtpHandler: ({required email}) {
        throw AuthFailure.connection();
      },
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();
    final context = tester.element(find.byKey(const Key('login-screen')));
    GoRouter.of(context).go('/forgot-password');
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const Key('forgot-password-email-field')),
      'pavel@example.com',
    );
    await tester.tap(find.byKey(const Key('forgot-password-submit-button')));
    await tester.pumpAndSettle();

    expect(
      find.text('Unable to connect to the server. Please try again.'),
      findsOneWidget,
    );
  });

  testWidgets('forgot-password preserves generic reset-link alternative', (
    tester,
  ) async {
    useLargeTestSurface(tester);
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();
    final context = tester.element(find.byKey(const Key('login-screen')));
    GoRouter.of(context).go('/forgot-password');
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const Key('forgot-password-email-field')),
      '  PAVEL@EXAMPLE.COM  ',
    );
    await tester.tap(find.byKey(const Key('forgot-password-link-button')));
    await tester.pumpAndSettle();

    expect(repository.requestPasswordResetCalls, 1);
    expect(repository.lastPasswordResetRequestEmail, 'pavel@example.com');
    expect(
      find.text(
        'If an account with that email exists, password reset instructions have been sent.',
      ),
      findsOneWidget,
    );
  });

  testWidgets('missing reset token shows unavailable state without request', (
    tester,
  ) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoggedOutReset(tester, repository);

    expect(find.text('Password reset link unavailable'), findsOneWidget);
    expect(repository.confirmPasswordResetCalls, 0);
  });

  testWidgets('empty and oversized reset tokens are rejected locally', (
    tester,
  ) async {
    useLargeTestSurface(tester);
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();
    final context = tester.element(find.byKey(const Key('login-screen')));
    final router = GoRouter.of(context);

    router.go('/reset-password?token=');
    await tester.pumpAndSettle();
    expect(find.text('Password reset link unavailable'), findsOneWidget);

    final oversized = List.filled(513, 'a').join();
    router.go('/reset-password?token=${Uri.encodeQueryComponent(oversized)}');
    await tester.pumpAndSettle();

    expect(find.text('Password reset link unavailable'), findsOneWidget);
    expect(repository.confirmPasswordResetCalls, 0);
  });

  testWidgets('reset validates password policy and confirmation locally', (
    tester,
  ) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoggedOutReset(tester, repository, token: 'valid-token');

    await tester.enterText(
      find.byKey(const Key('reset-password-field')),
      'short',
    );
    await tester.enterText(
      find.byKey(const Key('reset-password-confirm-field')),
      'different',
    );
    await tester.tap(find.byKey(const Key('reset-password-submit-button')));
    await tester.pump();

    expect(
      find.text('Password must be at least 15 characters.'),
      findsOneWidget,
    );
    expect(find.text('Passwords do not match.'), findsOneWidget);
    expect(repository.confirmPasswordResetCalls, 0);
  });

  testWidgets('reset preserves password and never renders opaque token', (
    tester,
  ) async {
    const token = 'opaque-reset-token-never-render-me';
    const password = '  Mealio-new-password  ';
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoggedOutReset(tester, repository, token: token);
    await enterValidPassword(tester, password);
    await tester.tap(find.byKey(const Key('reset-password-submit-button')));
    await tester.pumpAndSettle();

    expect(repository.confirmPasswordResetCalls, 1);
    expect(repository.lastPasswordResetToken, token);
    expect(repository.lastPasswordResetPassword, password);
    expect(repository.logoutCalls, 0);
    expect(find.text('Password reset complete'), findsOneWidget);
    expect(find.textContaining(token), findsNothing);
  });

  testWidgets('reset submit prevents duplicate confirmation', (tester) async {
    final completer = Completer<void>();
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      confirmPasswordResetHandler: ({required token, required newPassword}) =>
          completer.future,
    );

    await openLoggedOutReset(tester, repository, token: 'single-use-token');
    await enterValidPassword(tester, 'Mealio-new-password-123');

    await tester.tap(find.byKey(const Key('reset-password-submit-button')));
    await tester.tap(find.byKey(const Key('reset-password-submit-button')));
    await tester.pump();

    expect(repository.confirmPasswordResetCalls, 1);
    expect(
      find.byKey(const Key('reset-password-loading-indicator')),
      findsOneWidget,
    );

    completer.complete();
    await tester.pumpAndSettle();
    expect(find.text('Password reset complete'), findsOneWidget);
  });

  testWidgets('invalid consumed reset token is generic and not rendered', (
    tester,
  ) async {
    const token = 'consumed-secret-reset-token';
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      confirmPasswordResetHandler: ({required token, required newPassword}) {
        throw AuthFailure.invalidPasswordReset();
      },
    );

    await openLoggedOutReset(tester, repository, token: token);
    await enterValidPassword(tester, 'Mealio-new-password-123');
    await tester.tap(find.byKey(const Key('reset-password-submit-button')));
    await tester.pumpAndSettle();

    expect(find.text('Password reset link unavailable'), findsOneWidget);
    expect(
      find.text('This password reset link is invalid or has expired.'),
      findsOneWidget,
    );
    expect(find.textContaining(token), findsNothing);
  });

  testWidgets('cold-start reset route does not auto-confirm token', (
    tester,
  ) async {
    useLargeTestSurface(tester);
    final restoreCompleter = Completer<AuthUser?>();
    final repository = FakeAuthRepository(
      restoreHandler: () => restoreCompleter.future,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pump();

    final context = tester.element(find.byKey(const Key('splash-screen')));
    GoRouter.of(context).go('/reset-password?token=cold-start-token');
    await tester.pump();
    await tester.pump();

    expect(find.byKey(const Key('reset-password-screen')), findsOneWidget);
    expect(find.byKey(const Key('reset-password-field')), findsOneWidget);
    expect(repository.confirmPasswordResetCalls, 0);

    restoreCompleter.complete(null);
    await tester.pumpAndSettle();

    expect(repository.confirmPasswordResetCalls, 0);
    expect(find.byKey(const Key('reset-password-screen')), findsOneWidget);
  });

  testWidgets('cold-start reset submit waits for auth restoration', (
    tester,
  ) async {
    useLargeTestSurface(tester);
    final restoreCompleter = Completer<AuthUser?>();
    final repository = FakeAuthRepository(
      restoreHandler: () => restoreCompleter.future,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pump();
    final context = tester.element(find.byKey(const Key('splash-screen')));
    GoRouter.of(context).go('/reset-password?token=cold-submit-token');
    await tester.pump();
    await tester.pump();

    await enterValidPassword(tester, 'Mealio-new-password-123');
    await tester.tap(find.byKey(const Key('reset-password-submit-button')));
    await tester.pump();

    expect(repository.confirmPasswordResetCalls, 0);

    restoreCompleter.complete(null);
    await tester.pumpAndSettle();

    expect(repository.confirmPasswordResetCalls, 1);
    expect(find.text('Password reset complete'), findsOneWidget);
  });

  testWidgets('authenticated reset clears global session after success', (
    tester,
  ) async {
    useLargeTestSurface(tester);
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    final context = tester.element(find.byKey(const Key('home-screen')));
    GoRouter.of(context).go('/reset-password?token=authenticated-reset-token');
    await tester.pumpAndSettle();

    await enterValidPassword(tester, 'Mealio-new-password-123');
    await tester.tap(find.byKey(const Key('reset-password-submit-button')));
    await tester.pumpAndSettle();

    expect(repository.confirmPasswordResetCalls, 1);
    expect(repository.logoutCalls, 1);
    expect(find.text('Password reset complete'), findsOneWidget);

    final screenContext = tester.element(
      find.byKey(const Key('reset-password-screen')),
    );
    final container = ProviderScope.containerOf(screenContext);
    expect(
      container.read(authControllerProvider).asData?.value.isAuthenticated,
      isFalse,
    );
  });
}
