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
    tester.view.physicalSize = const Size(1080, 3200);
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

  Future<void> openLoggedOutOtpReset(
    WidgetTester tester,
    FakeAuthRepository repository, {
    String? email = 'pavel@example.com',
  }) async {
    useLargeTestSurface(tester);
    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    final context = tester.element(find.byKey(const Key('login-screen')));
    GoRouter.of(context).go('/reset-password/code', extra: email);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('password-reset-otp-screen')), findsOneWidget);
  }

  Future<void> enterValidReset(
    WidgetTester tester, {
    String code = '001234',
    String password = 'Mealio-new-password-123',
  }) async {
    await tester.enterText(
      find.byKey(const Key('password-reset-otp-code-field')),
      code,
    );
    await tester.enterText(
      find.byKey(const Key('password-reset-otp-password-field')),
      password,
    );
    await tester.enterText(
      find.byKey(const Key('password-reset-otp-confirm-password-field')),
      password,
    );
  }

  testWidgets('missing OTP reset email shows unavailable state', (
    tester,
  ) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoggedOutOtpReset(tester, repository, email: null);

    expect(find.text('Password reset code unavailable'), findsOneWidget);
    expect(repository.confirmPasswordResetOtpCalls, 0);
    expect(repository.requestPasswordResetOtpCalls, 0);
  });

  testWidgets('OTP reset validates ASCII code and password locally', (
    tester,
  ) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);
    await openLoggedOutOtpReset(tester, repository);

    await tester.enterText(
      find.byKey(const Key('password-reset-otp-code-field')),
      '12345',
    );
    await tester.enterText(
      find.byKey(const Key('password-reset-otp-password-field')),
      'short',
    );
    await tester.enterText(
      find.byKey(const Key('password-reset-otp-confirm-password-field')),
      'different',
    );
    await tester.tap(find.byKey(const Key('password-reset-otp-submit-button')));
    await tester.pump();

    expect(
      find.text('Enter the six-digit code from your email.'),
      findsOneWidget,
    );
    expect(
      find.text('Password must be at least 15 characters.'),
      findsOneWidget,
    );
    expect(find.text('Passwords do not match.'), findsOneWidget);
    expect(repository.confirmPasswordResetOtpCalls, 0);
  });

  testWidgets('OTP reset rejects whitespace-only and oversized passwords', (
    tester,
  ) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);
    await openLoggedOutOtpReset(tester, repository);

    await enterValidReset(tester, password: '               ');
    await tester.tap(find.byKey(const Key('password-reset-otp-submit-button')));
    await tester.pump();
    expect(
      find.text('Password cannot contain only whitespace.'),
      findsOneWidget,
    );

    final oversized = List.filled(129, 'a').join();
    await tester.enterText(
      find.byKey(const Key('password-reset-otp-password-field')),
      oversized,
    );
    await tester.enterText(
      find.byKey(const Key('password-reset-otp-confirm-password-field')),
      oversized,
    );
    await tester.tap(find.byKey(const Key('password-reset-otp-submit-button')));
    await tester.pump();

    expect(
      find.text('Password must be 128 characters or fewer.'),
      findsOneWidget,
    );
    expect(repository.confirmPasswordResetOtpCalls, 0);
  });

  testWidgets(
    'OTP reset clears tokens after failed restore and preserves inputs',
    (tester) async {
      const password = '  Mealio-new-password  ';
      final repository = FakeAuthRepository(
        restoreHandler: () async => throw AuthFailure.connection(),
      );
      await openLoggedOutOtpReset(
        tester,
        repository,
        email: '  PAVEL@EXAMPLE.COM  ',
      );

      await enterValidReset(tester, code: '001234', password: password);
      await tester.tap(
        find.byKey(const Key('password-reset-otp-submit-button')),
      );
      await tester.pumpAndSettle();

      expect(repository.confirmPasswordResetOtpCalls, 1);
      expect(repository.lastPasswordResetOtpConfirmEmail, 'pavel@example.com');
      expect(repository.lastPasswordResetOtpCode, '001234');
      expect(repository.lastPasswordResetOtpPassword, password);
      expect(repository.logoutCalls, 1);
      expect(find.text('Password reset complete'), findsOneWidget);
      expect(
        find.byKey(const Key('password-reset-otp-code-field')),
        findsNothing,
      );
      expect(find.textContaining('001234'), findsNothing);
      expect(find.textContaining(password), findsNothing);
    },
  );

  testWidgets('OTP reset prevents duplicate confirmation', (tester) async {
    final completer = Completer<void>();
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      confirmPasswordResetOtpHandler:
          ({required email, required code, required newPassword}) =>
              completer.future,
    );
    await openLoggedOutOtpReset(tester, repository);
    await enterValidReset(tester);

    final submit = find.byKey(const Key('password-reset-otp-submit-button'));
    await tester.tap(submit);
    await tester.tap(submit);
    await tester.pump();

    expect(repository.confirmPasswordResetOtpCalls, 1);
    expect(
      find.byKey(const Key('password-reset-otp-submit-loading')),
      findsOneWidget,
    );

    completer.complete();
    await tester.pumpAndSettle();
    expect(find.text('Password reset complete'), findsOneWidget);
  });

  testWidgets('invalid OTP failure is generic and clears secret code', (
    tester,
  ) async {
    const code = '654321';
    const password = 'Private-password-654321';
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      confirmPasswordResetOtpHandler:
          ({required email, required code, required newPassword}) {
            throw AuthFailure.invalidPasswordResetOtp();
          },
    );
    await openLoggedOutOtpReset(tester, repository);
    await enterValidReset(tester, code: code, password: password);
    await tester.tap(find.byKey(const Key('password-reset-otp-submit-button')));
    await tester.pumpAndSettle();

    expect(
      find.text('Invalid or expired password reset code.'),
      findsOneWidget,
    );
    final codeField = tester.widget<TextFormField>(
      find.byKey(const Key('password-reset-otp-code-field')),
    );
    expect(codeField.controller?.text, isEmpty);
  });

  testWidgets('OTP resend is generic and duplicate-safe', (tester) async {
    final completer = Completer<void>();
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      requestPasswordResetOtpHandler: ({required email}) => completer.future,
    );
    await openLoggedOutOtpReset(tester, repository);
    await tester.enterText(
      find.byKey(const Key('password-reset-otp-code-field')),
      '123456',
    );

    final resend = find.byKey(const Key('password-reset-otp-resend-button'));
    await tester.tap(resend);
    await tester.tap(resend);
    await tester.pump();

    expect(repository.requestPasswordResetOtpCalls, 1);
    expect(repository.lastPasswordResetOtpRequestEmail, 'pavel@example.com');
    expect(
      find.byKey(const Key('password-reset-otp-resend-loading')),
      findsOneWidget,
    );

    completer.complete();
    await tester.pumpAndSettle();
    final codeField = tester.widget<TextFormField>(
      find.byKey(const Key('password-reset-otp-code-field')),
    );
    expect(codeField.controller?.text, isEmpty);
    expect(
      find.text(
        'If an account with that email exists, a password reset code has been sent.',
      ),
      findsOneWidget,
    );
  });

  testWidgets('OTP reset route remains public during cold start', (
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
    GoRouter.of(context).go('/reset-password/code', extra: 'pavel@example.com');
    await tester.pump();
    await tester.pump();

    expect(find.byKey(const Key('password-reset-otp-screen')), findsOneWidget);
    expect(repository.confirmPasswordResetOtpCalls, 0);

    restoreCompleter.complete(null);
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('password-reset-otp-screen')), findsOneWidget);
  });

  testWidgets('cold-start OTP submit waits for auth restoration', (
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
    GoRouter.of(context).go('/reset-password/code', extra: 'pavel@example.com');
    await tester.pump();
    await tester.pump();
    await enterValidReset(tester);
    await tester.tap(find.byKey(const Key('password-reset-otp-submit-button')));
    await tester.pump();

    expect(repository.confirmPasswordResetOtpCalls, 0);
    restoreCompleter.complete(null);
    await tester.pumpAndSettle();

    expect(repository.confirmPasswordResetOtpCalls, 1);
    expect(find.text('Password reset complete'), findsOneWidget);
  });

  testWidgets('authenticated OTP reset clears global session after success', (
    tester,
  ) async {
    useLargeTestSurface(tester);
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();
    final context = tester.element(find.byKey(const Key('home-screen')));
    GoRouter.of(context).go('/reset-password/code', extra: 'pavel@example.com');
    await tester.pumpAndSettle();
    await enterValidReset(tester);
    await tester.tap(find.byKey(const Key('password-reset-otp-submit-button')));
    await tester.pumpAndSettle();

    expect(repository.confirmPasswordResetOtpCalls, 1);
    expect(repository.logoutCalls, 1);
    expect(find.text('Password reset complete'), findsOneWidget);

    final screenContext = tester.element(
      find.byKey(const Key('password-reset-otp-screen')),
    );
    final container = ProviderScope.containerOf(screenContext);
    expect(
      container.read(authControllerProvider).asData?.value.isAuthenticated,
      isFalse,
    );
  });
}
