import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mealio/app/app.dart';
import 'package:mealio/features/auth/data/auth_repository.dart';
import 'package:mealio/features/auth/domain/auth_failure.dart';
import 'package:mealio/features/auth/domain/auth_user.dart';

import 'helpers/auth_test_fakes.dart';

void main() {
  final emailOnlyUser = AuthUser(
    id: '31ca8c3a-90fd-46bf-a981-d541627862f3',
    email: 'fallback@example.com',
    fullName: null,
    createdAt: DateTime.parse('2026-07-20T10:00:00Z'),
    updatedAt: DateTime.parse('2026-07-20T10:00:00Z'),
  );

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
    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('login-screen')), findsOneWidget);
  }

  Future<void> enterValidCredentials(WidgetTester tester) async {
    await tester.enterText(
      find.byKey(const Key('login-email-field')),
      'pavel@example.com',
    );
    await tester.enterText(
      find.byKey(const Key('login-password-field')),
      'test-password',
    );
  }

  testWidgets(
    'application starts with Splash while auth initialization is unresolved',
    (tester) async {
      final completer = Completer<AuthUser?>();
      final repository = FakeAuthRepository(
        restoreHandler: () => completer.future,
      );

      await tester.pumpWidget(createApp(repository));
      await tester.pump();

      expect(find.byKey(const Key('splash-screen')), findsOneWidget);

      completer.complete(null);
      await tester.pumpAndSettle();
    },
  );

  testWidgets('no session routes to Login', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoginScreen(tester, repository);

    expect(find.byKey(const Key('login-email-field')), findsOneWidget);
    expect(find.byKey(const Key('login-password-field')), findsOneWidget);
  });

  testWidgets('valid session routes to Home', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('home-screen')), findsOneWidget);
  });

  testWidgets('Login contains email and password fields', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoginScreen(tester, repository);

    expect(find.byKey(const Key('login-email-field')), findsOneWidget);
    expect(find.byKey(const Key('login-password-field')), findsOneWidget);
  });

  testWidgets('empty email fails validation', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoginScreen(tester, repository);
    await tester.enterText(
      find.byKey(const Key('login-password-field')),
      'test-password',
    );
    await tester.tap(find.byKey(const Key('login-button')));
    await tester.pump();

    expect(find.text('Email is required.'), findsOneWidget);
    expect(repository.loginCalls, 0);
  });

  testWidgets('invalid email fails validation', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoginScreen(tester, repository);
    await tester.enterText(
      find.byKey(const Key('login-email-field')),
      'not-an-email',
    );
    await tester.enterText(
      find.byKey(const Key('login-password-field')),
      'test-password',
    );
    await tester.tap(find.byKey(const Key('login-button')));
    await tester.pump();

    expect(find.text('Enter a valid email address.'), findsOneWidget);
    expect(repository.loginCalls, 0);
  });

  testWidgets('empty password fails validation', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoginScreen(tester, repository);
    await tester.enterText(
      find.byKey(const Key('login-email-field')),
      'pavel@example.com',
    );
    await tester.tap(find.byKey(const Key('login-button')));
    await tester.pump();

    expect(find.text('Password is required.'), findsOneWidget);
    expect(repository.loginCalls, 0);
  });

  testWidgets('invalid form never calls repository', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoginScreen(tester, repository);
    await tester.tap(find.byKey(const Key('login-button')));
    await tester.pump();

    expect(repository.loginCalls, 0);
  });

  testWidgets('valid form calls login', (tester) async {
    final loginCompleter = Completer<AuthUser>();
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      loginHandler: ({required String email, required String password}) =>
          loginCompleter.future,
    );

    await openLoginScreen(tester, repository);
    await enterValidCredentials(tester);
    await tester.tap(find.byKey(const Key('login-button')));
    await tester.pump();

    expect(repository.loginCalls, 1);
    expect(repository.lastLoginEmail, 'pavel@example.com');

    loginCompleter.complete(testAuthUser);
    await tester.pumpAndSettle();
  });

  testWidgets('keyboard submit calls login', (tester) async {
    final loginCompleter = Completer<AuthUser>();
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      loginHandler: ({required String email, required String password}) =>
          loginCompleter.future,
    );

    await openLoginScreen(tester, repository);
    await enterValidCredentials(tester);
    await tester.tap(find.byKey(const Key('login-password-field')));
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pump();

    expect(repository.loginCalls, 1);

    loginCompleter.complete(testAuthUser);
    await tester.pumpAndSettle();
  });

  testWidgets('login loading indicator appears', (tester) async {
    final loginCompleter = Completer<AuthUser>();
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      loginHandler: ({required String email, required String password}) =>
          loginCompleter.future,
    );

    await openLoginScreen(tester, repository);
    await enterValidCredentials(tester);
    await tester.tap(find.byKey(const Key('login-button')));
    await tester.pump();

    expect(find.byKey(const Key('login-loading-indicator')), findsOneWidget);

    loginCompleter.complete(testAuthUser);
    await tester.pumpAndSettle();
  });

  testWidgets('login button is disabled while login is pending', (
    tester,
  ) async {
    final loginCompleter = Completer<AuthUser>();
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      loginHandler: ({required String email, required String password}) =>
          loginCompleter.future,
    );

    await openLoginScreen(tester, repository);
    await enterValidCredentials(tester);
    await tester.tap(find.byKey(const Key('login-button')));
    await tester.pump();

    final button = tester.widget<FilledButton>(
      find.byKey(const Key('login-button')),
    );

    expect(button.onPressed, isNull);

    loginCompleter.complete(testAuthUser);
    await tester.pumpAndSettle();
  });

  testWidgets('login success redirects to Home', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      loginHandler: ({required String email, required String password}) async =>
          testAuthUser,
    );

    await openLoginScreen(tester, repository);
    await enterValidCredentials(tester);
    await tester.tap(find.byKey(const Key('login-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('home-screen')), findsOneWidget);
  });

  testWidgets('wrong credentials show safe error message', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      loginHandler: ({required String email, required String password}) {
        throw AuthFailure.invalidCredentials();
      },
    );

    await openLoginScreen(tester, repository);
    await enterValidCredentials(tester);
    await tester.tap(find.byKey(const Key('login-button')));
    await tester.pumpAndSettle();

    expect(find.text('Invalid email or password.'), findsOneWidget);
  });

  testWidgets('input values remain after login error', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => null,
      loginHandler: ({required String email, required String password}) {
        throw AuthFailure.invalidCredentials();
      },
    );

    await openLoginScreen(tester, repository);
    await enterValidCredentials(tester);
    await tester.tap(find.byKey(const Key('login-button')));
    await tester.pumpAndSettle();

    final emailField = tester.widget<TextFormField>(
      find.byKey(const Key('login-email-field')),
    );
    final passwordField = tester.widget<TextFormField>(
      find.byKey(const Key('login-password-field')),
    );

    expect(emailField.controller?.text, 'pavel@example.com');
    expect(passwordField.controller?.text, 'test-password');
  });

  testWidgets('Home displays current user full name', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    expect(find.text('Good to see you, Pavel Potapenko'), findsOneWidget);
  });

  testWidgets('Home falls back to email when fullName is null', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => emailOnlyUser,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    expect(find.text('Good to see you, fallback@example.com'), findsOneWidget);
  });

  testWidgets('logout routes from Home to Login', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('home-logout-button')));
    await tester.pumpAndSettle();

    expect(repository.logoutCalls, 1);
    expect(find.byKey(const Key('login-screen')), findsOneWidget);
  });

  testWidgets('logout failure still routes from Home to Login', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
      logoutHandler: () async => throw AuthFailure.unexpected(),
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('home-logout-button')));
    await tester.pumpAndSettle();

    expect(repository.logoutCalls, 1);
    expect(find.byKey(const Key('home-screen')), findsNothing);
    expect(find.byKey(const Key('login-screen')), findsOneWidget);
    expect(find.text('Something went wrong. Please try again.'), findsOneWidget);
  });

  testWidgets('unauthenticated user cannot open Home', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoginScreen(tester, repository);

    final context = tester.element(find.byKey(const Key('login-screen')));
    GoRouter.of(context).go('/home');
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('login-screen')), findsOneWidget);
    expect(find.byKey(const Key('home-screen')), findsNothing);
  });

  testWidgets('authenticated user cannot remain on Login', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    final context = tester.element(find.byKey(const Key('home-screen')));
    GoRouter.of(context).go('/login');
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('home-screen')), findsOneWidget);
    expect(find.byKey(const Key('login-screen')), findsNothing);
  });

  testWidgets('Continue to Home no longer exists', (tester) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoginScreen(tester, repository);

    expect(find.byKey(const Key('continue-home-button')), findsNothing);
    expect(find.text('Continue to Home'), findsNothing);
  });

  testWidgets('Home keeps feature placeholders', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    expect(find.text('Pantry'), findsOneWidget);
    expect(find.text('AI Recipe'), findsOneWidget);
    expect(find.text('Meal Plan'), findsOneWidget);
    expect(find.text('Shopping List'), findsOneWidget);
  });
}
