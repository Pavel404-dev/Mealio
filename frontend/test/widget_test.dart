import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mealio/app/app.dart';
import 'package:mealio/features/auth/data/auth_repository.dart';
import 'package:mealio/features/auth/domain/auth_failure.dart';
import 'package:mealio/features/auth/domain/auth_user.dart';
import 'package:mealio/features/pantry/data/pantry_repository.dart';
import 'package:mealio/features/pantry/domain/pantry_item.dart';
import 'package:mealio/features/pantry/presentation/pantry_providers.dart';

import 'helpers/auth_test_fakes.dart';

void main() {
  final emailOnlyUser = AuthUser(
    id: '31ca8c3a-90fd-46bf-a981-d541627862f3',
    email: 'fallback@example.com',
    fullName: null,
    createdAt: DateTime.parse('2026-07-20T10:00:00Z'),
    updatedAt: DateTime.parse('2026-07-20T10:00:00Z'),
  );

  Widget createApp(
    FakeAuthRepository repository, {
    PantryRepository? pantryRepository,
  }) {
    return ProviderScope(
      overrides: [
        authRepositoryProvider.overrideWithValue(repository),
        pantryRepositoryProvider.overrideWithValue(
          pantryRepository ?? _RouterPantryRepository(),
        ),
        pantryItemsProvider.overrideWith((ref) async => []),
      ],
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
    expect(
      find.text('Something went wrong. Please try again.'),
      findsOneWidget,
    );
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

  testWidgets('authenticated Home Pantry tap opens Pantry', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('pantry-card')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('pantry-screen')), findsOneWidget);
    expect(
      find.text('Pantry will be implemented in a future PR.'),
      findsNothing,
    );
  });

  testWidgets('Back from Pantry returns to Home', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('pantry-card')));
    await tester.pumpAndSettle();

    await tester.pageBack();
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('home-screen')), findsOneWidget);
    expect(find.byKey(const Key('pantry-screen')), findsNothing);
  });

  testWidgets('Pantry Add opens creation flow and Back returns to Pantry', (
    tester,
  ) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('pantry-card')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('pantry-add-button')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('add-pantry-item-screen')), findsOneWidget);
    await tester.tap(find.byKey(const Key('add-pantry-back-button')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('pantry-screen')), findsOneWidget);
  });

  testWidgets('unauthenticated user cannot open Pantry directly', (
    tester,
  ) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoginScreen(tester, repository);
    final context = tester.element(find.byKey(const Key('login-screen')));
    GoRouter.of(context).go('/pantry');
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('login-screen')), findsOneWidget);
    expect(find.byKey(const Key('pantry-screen')), findsNothing);
  });

  testWidgets('authenticated user can open Pantry directly', (tester) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();
    final context = tester.element(find.byKey(const Key('home-screen')));
    GoRouter.of(context).go('/pantry');
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('pantry-screen')), findsOneWidget);
  });

  testWidgets(
    'authenticated user can open edit from Pantry and return with Back',
    (tester) async {
      final repository = FakeAuthRepository(
        restoreHandler: () async => testAuthUser,
      );
      await tester.pumpWidget(createApp(repository));
      await tester.pumpAndSettle();
      final homeContext = tester.element(find.byKey(const Key('home-screen')));
      GoRouter.of(homeContext).go('/pantry');
      await tester.pumpAndSettle();
      final pantryContext = tester.element(
        find.byKey(const Key('pantry-screen')),
      );
      GoRouter.of(
        pantryContext,
      ).push('/pantry/pantry-1/edit', extra: _routerPantryItem);
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('edit-pantry-item-screen')), findsOneWidget);

      await tester.tap(find.byKey(const Key('edit-pantry-back-button')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('pantry-screen')), findsOneWidget);
    },
  );

  testWidgets('production edit route replaces state for a new pantry item', (
    tester,
  ) async {
    final itemA = _routerPantryItemFor(
      id: 'pantry-a',
      ingredientId: 'ingredient-a',
      quantityG: 125.5,
      expiresAt: DateTime.parse('2026-10-01T18:30:00Z'),
      ingredientName: 'Beans',
    );
    final itemB = _routerPantryItemFor(
      id: 'pantry-b',
      ingredientId: 'ingredient-b',
      quantityG: 700,
      expiresAt: DateTime.parse('2026-12-03T06:45:00Z'),
      ingredientName: 'Rice',
    );
    final pantryRepository = _TrackingPantryRepository(
      updateHandler: (_, _, _) async => itemB,
    );
    final authRepository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
    );

    await tester.pumpWidget(
      createApp(authRepository, pantryRepository: pantryRepository),
    );
    await tester.pumpAndSettle();
    final homeContext = tester.element(find.byKey(const Key('home-screen')));
    final router = GoRouter.of(homeContext);
    router.go('/pantry/${itemA.id}/edit', extra: itemA);
    await tester.pumpAndSettle();
    router.go('/pantry/${itemB.id}/edit', extra: itemB);
    await tester.pumpAndSettle();

    expect(find.text('Rice'), findsOneWidget);
    expect(
      tester
          .widget<TextFormField>(
            find.byKey(const Key('edit-pantry-quantity-field')),
          )
          .controller
          ?.text,
      '700',
    );
    expect(find.text('2026-12-03'), findsOneWidget);

    await tester.tap(find.byKey(const Key('edit-pantry-save-button')));
    await tester.pumpAndSettle();

    expect(pantryRepository.updateCalls, 1);
    expect(pantryRepository.lastPantryItemId, itemB.id);
    expect(pantryRepository.lastQuantity, '700');
    expect(pantryRepository.lastExpiry, itemB.expiresAt);
    expect(find.byKey(const Key('pantry-screen')), findsOneWidget);
    expect(find.byKey(const Key('edit-pantry-item-screen')), findsNothing);
    expect(
      find.byKey(const Key('edit-pantry-delete-confirm-dialog')),
      findsNothing,
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'completion for replaced production edit does not affect the new item',
    (tester) async {
      final itemA = _routerPantryItemFor(
        id: 'pantry-a',
        ingredientId: 'ingredient-a',
        quantityG: 125.5,
        expiresAt: DateTime.parse('2026-10-01T18:30:00Z'),
        ingredientName: 'Beans',
      );
      final itemB = _routerPantryItemFor(
        id: 'pantry-b',
        ingredientId: 'ingredient-b',
        quantityG: 700,
        expiresAt: DateTime.parse('2026-12-03T06:45:00Z'),
        ingredientName: 'Rice',
      );
      final updateA = Completer<PantryItem>();
      final pantryRepository = _TrackingPantryRepository(
        updateHandler: (id, _, _) =>
            id == itemA.id ? updateA.future : Future.value(itemB),
      );
      final authRepository = FakeAuthRepository(
        restoreHandler: () async => testAuthUser,
      );

      await tester.pumpWidget(
        createApp(authRepository, pantryRepository: pantryRepository),
      );
      await tester.pumpAndSettle();
      final homeContext = tester.element(find.byKey(const Key('home-screen')));
      final router = GoRouter.of(homeContext);
      router.go('/pantry/${itemA.id}/edit', extra: itemA);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('edit-pantry-save-button')));
      await tester.pump();
      expect(pantryRepository.updateCalls, 1);
      expect(pantryRepository.lastPantryItemId, itemA.id);

      router.go('/pantry/${itemB.id}/edit', extra: itemB);
      await tester.pumpAndSettle();
      updateA.complete(itemA);
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('edit-pantry-item-screen')), findsOneWidget);
      expect(find.byKey(const Key('pantry-screen')), findsNothing);
      expect(find.text('Rice'), findsOneWidget);
      expect(
        tester
            .widget<TextFormField>(
              find.byKey(const Key('edit-pantry-quantity-field')),
            )
            .controller
            ?.text,
        '700',
      );
      expect(find.text('2026-12-03'), findsOneWidget);
      expect(find.byKey(const Key('edit-pantry-error-message')), findsNothing);
      expect(pantryRepository.updateCalls, 1);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('unauthenticated user cannot open pantry edit route', (
    tester,
  ) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);
    await openLoginScreen(tester, repository);
    final context = tester.element(find.byKey(const Key('login-screen')));
    GoRouter.of(context).go('/pantry/pantry-1/edit', extra: _routerPantryItem);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('login-screen')), findsOneWidget);
    expect(find.byKey(const Key('edit-pantry-item-screen')), findsNothing);
  });

  testWidgets(
    'malformed pantry edit routes return authenticated user to Pantry',
    (tester) async {
      final repository = FakeAuthRepository(
        restoreHandler: () async => testAuthUser,
      );
      await tester.pumpWidget(createApp(repository));
      await tester.pumpAndSettle();
      final context = tester.element(find.byKey(const Key('home-screen')));
      GoRouter.of(context).go('/pantry/pantry-1/edit');
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('pantry-screen')), findsOneWidget);
      expect(tester.takeException(), isNull);

      final pantryContext = tester.element(
        find.byKey(const Key('pantry-screen')),
      );
      GoRouter.of(
        pantryContext,
      ).go('/pantry/other-item/edit', extra: _routerPantryItem);
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('pantry-screen')), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('authenticated user can open Add Pantry directly', (
    tester,
  ) async {
    final repository = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
    );

    await tester.pumpWidget(createApp(repository));
    await tester.pumpAndSettle();
    final context = tester.element(find.byKey(const Key('home-screen')));
    GoRouter.of(context).go('/pantry/add');
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('add-pantry-item-screen')), findsOneWidget);
  });

  testWidgets('unauthenticated user cannot open Add Pantry directly', (
    tester,
  ) async {
    final repository = FakeAuthRepository(restoreHandler: () async => null);

    await openLoginScreen(tester, repository);
    final context = tester.element(find.byKey(const Key('login-screen')));
    GoRouter.of(context).go('/pantry/add');
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('login-screen')), findsOneWidget);
    expect(find.byKey(const Key('add-pantry-item-screen')), findsNothing);
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

    for (final feature in const [
      ('ai-recipe-card', 'AI Recipe'),
      ('meal-plan-card', 'Meal Plan'),
      ('shopping-list-card', 'Shopping List'),
    ]) {
      final card = find.byKey(Key(feature.$1));
      await tester.ensureVisible(card);
      await tester.tap(card);
      await tester.pump();
      expect(
        find.text('${feature.$2} will be implemented in a future PR.'),
        findsOneWidget,
      );
      ScaffoldMessenger.of(
        tester.element(find.byKey(const Key('home-screen'))),
      ).hideCurrentSnackBar();
      await tester.pumpAndSettle();
    }
  });
}

class _RouterPantryRepository implements PantryRepository {
  final Ingredient _ingredient = Ingredient(
    id: 'ingredient-1',
    name: 'Oats',
    category: 'grain',
    createdAt: DateTime.parse('2026-09-01T10:00:00Z'),
    nutritionValue: null,
  );

  @override
  Future<List<PantryItem>> getPantry() async => [];

  @override
  Future<List<Ingredient>> searchIngredients({String? search}) async => [
    _ingredient,
  ];

  @override
  Future<PantryItem> addPantryItem({
    required String ingredientId,
    required String quantityG,
    DateTime? expiresAt,
  }) async {
    return PantryItem(
      id: 'pantry-1',
      userId: 'user-1',
      ingredientId: ingredientId,
      quantityG: 1,
      expiresAt: expiresAt,
      createdAt: DateTime.parse('2026-09-10T10:00:00Z'),
      updatedAt: DateTime.parse('2026-09-10T10:00:00Z'),
      ingredient: _ingredient,
    );
  }

  @override
  Future<PantryItem> updatePantryItem({
    required String pantryItemId,
    required String quantityG,
    DateTime? expiresAt,
  }) => throw UnimplementedError();

  @override
  Future<void> deletePantryItem({required String pantryItemId}) =>
      throw UnimplementedError();
}

final _routerPantryItem = PantryItem(
  id: 'pantry-1',
  userId: 'user-1',
  ingredientId: 'ingredient-1',
  quantityG: 1,
  expiresAt: null,
  createdAt: DateTime.parse('2026-09-10T10:00:00Z'),
  updatedAt: DateTime.parse('2026-09-10T10:00:00Z'),
  ingredient: Ingredient(
    id: 'ingredient-1',
    name: 'Oats',
    category: 'grain',
    createdAt: DateTime.parse('2026-09-01T10:00:00Z'),
    nutritionValue: null,
  ),
);

Ingredient _routerIngredient({required String id, required String name}) {
  return Ingredient(
    id: id,
    name: name,
    category: 'grain',
    createdAt: DateTime.parse('2026-09-01T10:00:00Z'),
    nutritionValue: null,
  );
}

PantryItem _routerPantryItemFor({
  required String id,
  required String ingredientId,
  required String ingredientName,
  required double quantityG,
  required DateTime expiresAt,
}) {
  return PantryItem(
    id: id,
    userId: 'user-1',
    ingredientId: ingredientId,
    quantityG: quantityG,
    expiresAt: expiresAt,
    createdAt: DateTime.parse('2026-09-10T10:00:00Z'),
    updatedAt: DateTime.parse('2026-09-10T10:00:00Z'),
    ingredient: _routerIngredient(id: ingredientId, name: ingredientName),
  );
}

typedef _RouterUpdateHandler =
    Future<PantryItem> Function(
      String pantryItemId,
      String quantityG,
      DateTime? expiresAt,
    );

class _TrackingPantryRepository implements PantryRepository {
  _TrackingPantryRepository({this.updateHandler});

  final _RouterUpdateHandler? updateHandler;
  int updateCalls = 0;
  String? lastPantryItemId;
  String? lastQuantity;
  DateTime? lastExpiry;

  @override
  Future<List<PantryItem>> getPantry() async => [];

  @override
  Future<PantryItem> updatePantryItem({
    required String pantryItemId,
    required String quantityG,
    DateTime? expiresAt,
  }) {
    updateCalls++;
    lastPantryItemId = pantryItemId;
    lastQuantity = quantityG;
    lastExpiry = expiresAt;
    return updateHandler?.call(pantryItemId, quantityG, expiresAt) ??
        Future.error(UnimplementedError());
  }

  @override
  Future<List<Ingredient>> searchIngredients({String? search}) async => [];

  @override
  Future<PantryItem> addPantryItem({
    required String ingredientId,
    required String quantityG,
    DateTime? expiresAt,
  }) => Future.error(UnimplementedError());

  @override
  Future<void> deletePantryItem({required String pantryItemId}) =>
      Future.error(UnimplementedError());
}
