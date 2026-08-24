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

  Future<void> openLoggedOutOtpVerification(
    WidgetTester tester,
    FakeAuthRepository repository, {
    String email = 'registered@example.com',
  }) async {
    await openLoggedOutVerification(tester, repository, email: email);
    await tester.tap(find.byKey(const Key('verify-email-use-code-button')));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const Key('verify-email-otp-request-button')),
      findsOneWidget,
    );
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
      expect(repository.requestEmailVerificationOtpCalls, 0);
      expect(
        find.byKey(const Key('verify-email-use-code-button')),
        findsOneWidget,
      );
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

  testWidgets('OTP mode is explicit and switching performs no requests', (
    tester,
  ) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoggedOutOtpVerification(
      tester,
      repository,
      email: '  REGISTERED@EXAMPLE.COM  ',
    );

    expect(find.text('registered@example.com'), findsOneWidget);
    expect(repository.requestEmailVerificationOtpCalls, 0);
    expect(repository.confirmEmailVerificationOtpCalls, 0);

    await tester.enterText(
      find.byKey(const Key('verify-email-otp-field')),
      '001234',
    );
    await tester.tap(find.byKey(const Key('verify-email-use-link-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('verify-email-resend-button')), findsOneWidget);
    expect(repository.requestEmailVerificationOtpCalls, 0);
    expect(repository.confirmEmailVerificationOtpCalls, 0);

    await tester.tap(find.byKey(const Key('verify-email-use-code-button')));
    await tester.pumpAndSettle();

    final field = tester.widget<TextField>(
      find.byKey(const Key('verify-email-otp-field')),
    );
    expect(field.controller?.text, isEmpty);
  });

  testWidgets('OTP request blocks duplicates and shows generic success', (
    tester,
  ) async {
    final requestCompleter = Completer<void>();
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      requestEmailVerificationOtpHandler: ({required email}) =>
          requestCompleter.future,
    );

    await openLoggedOutOtpVerification(tester, repository);

    await tester.tap(find.byKey(const Key('verify-email-otp-request-button')));
    await tester.tap(find.byKey(const Key('verify-email-otp-request-button')));
    await tester.pump();

    expect(repository.requestEmailVerificationOtpCalls, 1);
    expect(
      repository.lastVerificationOtpRequestEmail,
      'registered@example.com',
    );
    expect(
      find.byKey(const Key('verify-email-otp-request-loading')),
      findsOneWidget,
    );

    requestCompleter.complete();
    await tester.pumpAndSettle();

    expect(
      find.text('If verification is needed, a code has been sent.'),
      findsOneWidget,
    );
  });

  testWidgets('OTP request failures use safe generic messages', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      requestEmailVerificationOtpHandler: ({required email}) {
        throw AuthFailure.rateLimited();
      },
    );

    await openLoggedOutOtpVerification(tester, repository);
    await tester.tap(find.byKey(const Key('verify-email-otp-request-button')));
    await tester.pumpAndSettle();

    expect(
      find.text('Too many requests. Please try again later.'),
      findsOneWidget,
    );
    expect(find.textContaining('registered@example.com is'), findsNothing);
  });

  testWidgets(
    'OTP input filters to six ASCII digits and preserves leading zeroes',
    (tester) async {
      final repository = FakeAuthRepository(restoreHandler: () async => null);

      await openLoggedOutOtpVerification(tester, repository);
      final otpField = find.byKey(const Key('verify-email-otp-field'));

      await tester.enterText(otpField, '00a12 34567٥٦٧');
      await tester.pump();

      final field = tester.widget<TextField>(otpField);
      expect(field.controller?.text, '001234');
      expect(field.keyboardType, TextInputType.number);
      expect(field.autofillHints, const [AutofillHints.oneTimeCode]);

      await tester.tap(
        find.byKey(const Key('verify-email-otp-confirm-button')),
      );
      await tester.pumpAndSettle();

      expect(repository.confirmEmailVerificationOtpCalls, 1);
      expect(
        repository.lastVerificationOtpConfirmEmail,
        'registered@example.com',
      );
      expect(repository.lastVerificationOtpCode, '001234');
      expect(find.text('Email verified'), findsOneWidget);

      await tester.tap(
        find.byKey(const Key('verify-email-success-continue-button')),
      );
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('login-screen')), findsOneWidget);
    },
  );

  testWidgets('incomplete OTP is not submitted', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoggedOutOtpVerification(tester, repository);
    await tester.enterText(
      find.byKey(const Key('verify-email-otp-field')),
      '00123',
    );
    await tester.pump();

    final button = tester.widget<FilledButton>(
      find.byKey(const Key('verify-email-otp-confirm-button')),
    );
    expect(button.onPressed, isNull);
    expect(repository.confirmEmailVerificationOtpCalls, 0);
  });

  testWidgets('OTP confirmation blocks duplicate submissions', (tester) async {
    final confirmCompleter = Completer<void>();
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      confirmEmailVerificationOtpHandler: ({required email, required code}) =>
          confirmCompleter.future,
    );

    await openLoggedOutOtpVerification(tester, repository);
    await tester.enterText(
      find.byKey(const Key('verify-email-otp-field')),
      '001234',
    );
    await tester.pump();
    await tester.tap(find.byKey(const Key('verify-email-otp-confirm-button')));
    await tester.tap(find.byKey(const Key('verify-email-otp-confirm-button')));
    await tester.pump();

    expect(repository.confirmEmailVerificationOtpCalls, 1);
    expect(
      find.byKey(const Key('verify-email-otp-confirm-loading')),
      findsOneWidget,
    );

    confirmCompleter.complete();
    await tester.pumpAndSettle();
    expect(find.text('Email verified'), findsOneWidget);
  });

  testWidgets('invalid OTP error is generic and does not echo the code', (
    tester,
  ) async {
    const code = '009876';
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      confirmEmailVerificationOtpHandler: ({required email, required code}) {
        throw AuthFailure.invalidEmailVerificationOtp();
      },
    );

    await openLoggedOutOtpVerification(tester, repository);
    await tester.enterText(
      find.byKey(const Key('verify-email-otp-field')),
      code,
    );
    await tester.pump();
    await tester.tap(find.byKey(const Key('verify-email-otp-confirm-button')));
    await tester.pumpAndSettle();

    final error = find.byKey(const Key('verify-email-otp-confirm-error'));
    expect(error, findsOneWidget);
    expect(
      find.descendant(of: error, matching: find.textContaining(code)),
      findsNothing,
    );
    expect(find.text('Invalid or expired verification code.'), findsOneWidget);
  });

  testWidgets('authenticated OTP success reloads current user from backend', (
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
    await tester.tap(find.byKey(const Key('verify-email-use-code-button')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('verify-email-otp-field')),
      '001234',
    );
    await tester.pump();
    await tester.tap(find.byKey(const Key('verify-email-otp-confirm-button')));
    await tester.pumpAndSettle();

    expect(repository.confirmEmailVerificationOtpCalls, 1);
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

  testWidgets('OTP sync retry does not reconfirm a consumed code', (
    tester,
  ) async {
    useLargeTestSurface(tester);
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
      currentUserHandler: () async {
        throw AuthFailure.connection();
      },
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    final context = tester.element(find.byKey(const Key('home-screen')));
    GoRouter.of(context).go('/verify-email');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('verify-email-use-code-button')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('verify-email-otp-field')),
      '001234',
    );
    await tester.pump();
    await tester.tap(find.byKey(const Key('verify-email-otp-confirm-button')));
    await tester.pumpAndSettle();

    expect(repository.confirmEmailVerificationOtpCalls, 1);
    expect(repository.currentUserCalls, 1);
    expect(
      find.byKey(const Key('verify-email-sync-retry-button')),
      findsOneWidget,
    );

    repository.currentUserHandler = () async => verifiedUser();
    await tester.tap(find.byKey(const Key('verify-email-sync-retry-button')));
    await tester.pumpAndSettle();

    expect(repository.confirmEmailVerificationOtpCalls, 1);
    expect(repository.currentUserCalls, 2);
    expect(find.text('Email verified'), findsOneWidget);
  });
}
