import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mealio/app/app.dart';
import 'package:mealio/features/auth/data/auth_repository.dart';
import 'package:mealio/features/auth/domain/auth_failure.dart';
import 'package:mealio/features/auth/domain/auth_user.dart';

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

  Future<void> openLoginScreen(
    WidgetTester tester,
    FakeAuthRepository repository,
  ) async {
    useLargeTestSurface(tester);
    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('login-screen')), findsOneWidget);
  }

  Future<void> openRegisterScreen(
    WidgetTester tester,
    FakeAuthRepository repository,
  ) async {
    await openLoginScreen(tester, repository);
    await tester.tap(find.byKey(const Key('open-register-button')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('register-screen')), findsOneWidget);
  }

  Future<void> enterValidRegistration(WidgetTester tester) async {
    await tester.enterText(
      find.byKey(const Key('register-full-name-field')),
      'Pavel Potapenko',
    );
    await tester.enterText(
      find.byKey(const Key('register-email-field')),
      'pavel@example.com',
    );
    await tester.enterText(
      find.byKey(const Key('register-password-field')),
      'Mealio-password-123',
    );
    await tester.enterText(
      find.byKey(const Key('register-confirm-password-field')),
      'Mealio-password-123',
    );
  }

  testWidgets('Register screen opens from Login', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openRegisterScreen(tester, repository);

    expect(find.text('Create your Mealio account'), findsOneWidget);
  });

  testWidgets('Register back button returns to Login', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openRegisterScreen(tester, repository);
    await tester.tap(find.byKey(const Key('register-back-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('login-screen')), findsOneWidget);
  });

  testWidgets('Already have an account returns to Login', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openRegisterScreen(tester, repository);
    await tester.tap(find.byKey(const Key('register-login-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('login-screen')), findsOneWidget);
  });

  testWidgets('required fields fail before repository call', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openRegisterScreen(tester, repository);
    await tester.tap(find.byKey(const Key('register-button')));
    await tester.pump();

    expect(find.text('Email is required.'), findsOneWidget);
    expect(find.text('Password is required.'), findsOneWidget);
    expect(find.text('Please confirm your password.'), findsOneWidget);
    expect(repository.registerCalls, 0);
  });

  testWidgets('invalid email fails before repository call', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openRegisterScreen(tester, repository);
    await tester.enterText(
      find.byKey(const Key('register-email-field')),
      'not-an-email',
    );
    await tester.enterText(
      find.byKey(const Key('register-password-field')),
      'Mealio-password-123',
    );
    await tester.enterText(
      find.byKey(const Key('register-confirm-password-field')),
      'Mealio-password-123',
    );
    await tester.tap(find.byKey(const Key('register-button')));
    await tester.pump();

    expect(find.text('Enter a valid email address.'), findsOneWidget);
    expect(repository.registerCalls, 0);
  });

  testWidgets('short password fails before repository call', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openRegisterScreen(tester, repository);
    await tester.enterText(
      find.byKey(const Key('register-email-field')),
      'pavel@example.com',
    );
    await tester.enterText(
      find.byKey(const Key('register-password-field')),
      '12345678901234',
    );
    await tester.enterText(
      find.byKey(const Key('register-confirm-password-field')),
      '12345678901234',
    );
    await tester.tap(find.byKey(const Key('register-button')));
    await tester.pump();

    expect(
      find.text('Password must be at least 15 characters.'),
      findsOneWidget,
    );
    expect(repository.registerCalls, 0);
  });

  testWidgets('password longer than backend maximum is rejected', (
    tester,
  ) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);
    final password = List.filled(129, 'a').join();

    await openRegisterScreen(tester, repository);
    await tester.enterText(
      find.byKey(const Key('register-email-field')),
      'pavel@example.com',
    );
    await tester.enterText(
      find.byKey(const Key('register-password-field')),
      password,
    );
    await tester.enterText(
      find.byKey(const Key('register-confirm-password-field')),
      password,
    );
    await tester.tap(find.byKey(const Key('register-button')));
    await tester.pump();

    expect(
      find.text('Password must be 128 characters or fewer.'),
      findsOneWidget,
    );
    expect(repository.registerCalls, 0);
  });

  testWidgets('whitespace-only password is rejected', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);
    const password = '               ';

    await openRegisterScreen(tester, repository);
    await tester.enterText(
      find.byKey(const Key('register-email-field')),
      'pavel@example.com',
    );
    await tester.enterText(
      find.byKey(const Key('register-password-field')),
      password,
    );
    await tester.enterText(
      find.byKey(const Key('register-confirm-password-field')),
      password,
    );
    await tester.tap(find.byKey(const Key('register-button')));
    await tester.pump();

    expect(
      find.text('Password cannot contain only whitespace.'),
      findsOneWidget,
    );
    expect(repository.registerCalls, 0);
  });

  testWidgets('password confirmation mismatch is rejected', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openRegisterScreen(tester, repository);
    await tester.enterText(
      find.byKey(const Key('register-email-field')),
      'pavel@example.com',
    );
    await tester.enterText(
      find.byKey(const Key('register-password-field')),
      'Mealio-password-123',
    );
    await tester.enterText(
      find.byKey(const Key('register-confirm-password-field')),
      'Mealio-password-456',
    );
    await tester.tap(find.byKey(const Key('register-button')));
    await tester.pump();

    expect(find.text('Passwords do not match.'), findsOneWidget);
    expect(repository.registerCalls, 0);
  });

  testWidgets('full name longer than backend maximum is rejected', (
    tester,
  ) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openRegisterScreen(tester, repository);
    await enterValidRegistration(tester);
    await tester.enterText(
      find.byKey(const Key('register-full-name-field')),
      List.filled(256, 'a').join(),
    );
    await tester.tap(find.byKey(const Key('register-button')));
    await tester.pump();

    expect(
      find.text('Full name must be 255 characters or fewer.'),
      findsOneWidget,
    );
    expect(repository.registerCalls, 0);
  });

  testWidgets('valid form calls registration exactly once', (tester) async {
    final completer = Completer<AuthUser>();
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      registerHandler: ({required email, required password, fullName}) =>
          completer.future,
    );

    await openRegisterScreen(tester, repository);
    await enterValidRegistration(tester);
    await tester.tap(find.byKey(const Key('register-button')));
    await tester.pump();

    expect(repository.registerCalls, 1);
    expect(repository.lastRegisterEmail, 'pavel@example.com');
    expect(repository.lastRegisterFullName, 'Pavel Potapenko');

    completer.complete(testAuthUser);
    await tester.pumpAndSettle();
  });

  testWidgets('registration loading disables actions and prevents duplicates', (
    tester,
  ) async {
    final completer = Completer<AuthUser>();
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      registerHandler: ({required email, required password, fullName}) =>
          completer.future,
    );

    await openRegisterScreen(tester, repository);
    await enterValidRegistration(tester);
    await tester.tap(find.byKey(const Key('register-button')));
    await tester.tap(find.byKey(const Key('register-button')));
    await tester.pump();

    expect(repository.registerCalls, 1);
    expect(find.byKey(const Key('register-loading-indicator')), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('register-button')))
          .onPressed,
      isNull,
    );
    expect(
      tester
          .widget<IconButton>(find.byKey(const Key('register-back-button')))
          .onPressed,
      isNull,
    );

    completer.complete(testAuthUser);
    await tester.pumpAndSettle();
  });

  testWidgets('duplicate email shows safe error', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      registerHandler: ({required email, required password, fullName}) {
        throw AuthFailure.duplicateEmail();
      },
    );

    await openRegisterScreen(tester, repository);
    await enterValidRegistration(tester);
    await tester.tap(find.byKey(const Key('register-button')));
    await tester.pumpAndSettle();

    expect(
      find.text('An account with this email already exists.'),
      findsOneWidget,
    );
  });

  testWidgets('network failure shows safe error', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      registerHandler: ({required email, required password, fullName}) {
        throw AuthFailure.connection();
      },
    );

    await openRegisterScreen(tester, repository);
    await enterValidRegistration(tester);
    await tester.tap(find.byKey(const Key('register-button')));
    await tester.pumpAndSettle();

    expect(
      find.text('Unable to connect to the server. Please try again.'),
      findsOneWidget,
    );
  });

  testWidgets('backend validation failure shows safe error', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      registerHandler: ({required email, required password, fullName}) {
        throw AuthFailure.registrationValidation();
      },
    );

    await openRegisterScreen(tester, repository);
    await enterValidRegistration(tester);
    await tester.tap(find.byKey(const Key('register-button')));
    await tester.pumpAndSettle();

    expect(find.text('Please check the registration details.'), findsOneWidget);
  });

  testWidgets('unexpected registration exception shows safe error', (
    tester,
  ) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      registerHandler: ({required email, required password, fullName}) {
        throw StateError('internal failure');
      },
    );

    await openRegisterScreen(tester, repository);
    await enterValidRegistration(tester);
    await tester.tap(find.byKey(const Key('register-button')));
    await tester.pumpAndSettle();

    expect(
      find.text('Something went wrong. Please try again.'),
      findsOneWidget,
    );
    expect(find.textContaining('StateError'), findsNothing);
    expect(find.textContaining('internal failure'), findsNothing);
  });

  testWidgets('successful registration returns to Login with prefilled email', (
    tester,
  ) async {
    final registeredUser = AuthUser(
      id: testAuthUser.id,
      email: 'normalized@example.com',
      fullName: testAuthUser.fullName,
      createdAt: testAuthUser.createdAt,
      updatedAt: testAuthUser.updatedAt,
    );
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      registerHandler: ({required email, required password, fullName}) async =>
          registeredUser,
    );

    await openRegisterScreen(tester, repository);
    await enterValidRegistration(tester);
    await tester.tap(find.byKey(const Key('register-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('login-screen')), findsOneWidget);
    expect(
      find.byKey(const Key('registration-success-message')),
      findsOneWidget,
    );
    expect(
      find.text('Account created successfully. You can now sign in.'),
      findsOneWidget,
    );
    final emailField = tester.widget<TextFormField>(
      find.byKey(const Key('login-email-field')),
    );
    expect(emailField.controller?.text, 'normalized@example.com');
  });

  testWidgets('login failure is visible after successful registration', (
    tester,
  ) async {
    final registeredUser = AuthUser(
      id: testAuthUser.id,
      email: 'normalized@example.com',
      fullName: testAuthUser.fullName,
      createdAt: testAuthUser.createdAt,
      updatedAt: testAuthUser.updatedAt,
    );

    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      registerHandler: ({required email, required password, fullName}) async =>
          registeredUser,
      loginHandler: ({required email, required password}) {
        throw AuthFailure.invalidCredentials();
      },
    );

    await openRegisterScreen(tester, repository);
    await enterValidRegistration(tester);
    await tester.tap(find.byKey(const Key('register-button')));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const Key('registration-success-message')),
      findsOneWidget,
    );

    await tester.enterText(
      find.byKey(const Key('login-password-field')),
      'Wrong-password-123',
    );
    await tester.tap(find.byKey(const Key('login-button')));
    await tester.pumpAndSettle();

    expect(repository.loginCalls, 1);
    expect(find.text('Invalid email or password.'), findsOneWidget);
    expect(find.byKey(const Key('registration-success-message')), findsNothing);
  });

  testWidgets('authenticated user cannot remain on Register', (tester) async {
    useLargeTestSurface(tester);
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    final context = tester.element(find.byKey(const Key('home-screen')));
    GoRouter.of(context).go('/register');
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('home-screen')), findsOneWidget);
    expect(find.byKey(const Key('register-screen')), findsNothing);
  });

  testWidgets('registration route does not bypass protected Home', (
    tester,
  ) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openRegisterScreen(tester, repository);
    final context = tester.element(find.byKey(const Key('register-screen')));
    GoRouter.of(context).go('/home');
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('login-screen')), findsOneWidget);
    expect(find.byKey(const Key('home-screen')), findsNothing);
  });
}
