import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/app/app.dart';
import 'package:mealio/app/router/app_router.dart';
import 'package:mealio/core/localization/locale_controller.dart';
import 'package:mealio/features/auth/data/auth_repository.dart';
import 'package:mealio/features/auth/domain/auth_failure.dart';
import 'package:mealio/features/auth/domain/auth_user.dart';
import 'package:mealio/features/pantry/data/pantry_repository.dart';
import 'package:mealio/features/pantry/domain/pantry_failure.dart';
import 'package:mealio/features/pantry/domain/pantry_item.dart';
import 'package:mealio/l10n/generated/app_localizations.dart';

import '../../helpers/auth_test_fakes.dart';
import '../../helpers/locale_test_fakes.dart';

void main() {
  Future<ProviderContainer> pumpApp(
    WidgetTester tester, {
    MemoryLocaleStorage? storage,
    FakeAuthRepository? auth,
    _PantryRepository? pantry,
    bool settle = true,
  }) async {
    final container = ProviderContainer(
      overrides: [
        localeStorageProvider.overrideWithValue(
          storage ?? MemoryLocaleStorage(),
        ),
        authRepositoryProvider.overrideWithValue(auth ?? FakeAuthRepository()),
        pantryRepositoryProvider.overrideWithValue(
          pantry ?? _PantryRepository(),
        ),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(container: container, child: const MealioApp()),
    );
    if (settle) await tester.pumpAndSettle();
    return container;
  }

  Future<void> tap(WidgetTester tester, String key) async {
    final finder = find.byKey(Key(key));
    await tester.ensureVisible(finder);
    await tester.pumpAndSettle();
    await tester.tap(finder);
    await tester.pumpAndSettle();
  }

  Future<void> changeLocale(
    WidgetTester tester,
    ProviderContainer container,
    String code,
  ) async {
    await container
        .read(localeControllerProvider.notifier)
        .setLocale(Locale(code));
    await tester.pumpAndSettle();
  }

  for (final code in ['en', 'ru', 'uk', 'sk']) {
    testWidgets(
      '$code system locale localizes login, validators and safe auth errors',
      (tester) async {
        tester.binding.platformDispatcher.localesTestValue = [
          Locale(code, 'XX'),
        ];
        addTearDown(tester.binding.platformDispatcher.clearLocalesTestValue);
        final l10n = await AppLocalizations.delegate.load(Locale(code));
        final container = await pumpApp(
          tester,
          auth: FakeAuthRepository(
            loginHandler: ({required email, required password}) async =>
                throw const AuthFailure(
                  type: AuthFailureType.invalidCredentials,
                  message: 'synthetic-private',
                ),
          ),
        );
        final screen = tester.element(find.byKey(const Key('login-screen')));
        expect(Localizations.localeOf(screen).languageCode, code);
        expect(find.text(l10n.welcome), findsOneWidget);
        await tap(tester, 'login-button');
        expect(find.text(l10n.emailRequired), findsOneWidget);
        expect(find.text(l10n.passwordRequired), findsOneWidget);
        await tester.enterText(
          find.byKey(const Key('login-email-field')),
          'test@example.com',
        );
        await tester.enterText(
          find.byKey(const Key('login-password-field')),
          'synthetic password',
        );
        await tap(tester, 'login-button');
        expect(find.text(l10n.authInvalidCredentials), findsOneWidget);
        expect(find.text('synthetic-private'), findsNothing);
        expect(container.read(appRouterProvider).state.uri.path, '/login');
      },
    );

    testWidgets(
      '$code localizes home, pantry empty state, add form and search error',
      (tester) async {
        final l10n = await AppLocalizations.delegate.load(Locale(code));
        final pantry = _PantryRepository();
        final container = await pumpApp(
          tester,
          storage: MemoryLocaleStorage(code),
          auth: FakeAuthRepository(restoreHandler: () async => testAuthUser),
          pantry: pantry,
        );
        expect(
          find.text(l10n.greetingNamed(testAuthUser.fullName!)),
          findsOneWidget,
        );
        expect(find.byTooltip(l10n.logout), findsOneWidget);
        expect(find.byTooltip(l10n.language), findsOneWidget);
        await tap(tester, 'pantry-card');
        expect(find.text(l10n.pantryEmpty), findsOneWidget);
        await tap(tester, 'pantry-add-button');
        expect(find.text(l10n.searchIngredients), findsOneWidget);
        expect(find.text(l10n.noIngredients), findsOneWidget);
        await tap(tester, 'add-pantry-submit-button');
        expect(find.text(l10n.quantityRequired), findsOneWidget);
        expect(find.text(l10n.selectIngredient), findsOneWidget);
        pantry.searchFailure = true;
        await tester.enterText(
          find.byKey(const Key('ingredient-search-field')),
          'oats',
        );
        await tester.pump(const Duration(milliseconds: 400));
        await tester.pumpAndSettle();
        expect(find.text(l10n.pantrySearchError), findsOneWidget);
        pantry.searchFailure = false;
        pantry.ingredients = [_ingredient];
        await tap(tester, 'ingredient-search-retry-button');
        await tap(tester, 'ingredient-result-ingredient-1');
        expect(find.text('Server Oats'), findsWidgets);
        await tester.enterText(
          find.byKey(const Key('pantry-quantity-field')),
          '500,25',
        );
        await tap(tester, 'add-pantry-submit-button');
        expect(find.text(l10n.pantryCreateError), findsOneWidget);
        expect(pantry.lastQuantity, '500.25');

        expect(container.read(appRouterProvider).state.uri.path, '/pantry/add');
      },
    );

    testWidgets('$code localizes splash during session restoration', (
      tester,
    ) async {
      final pending = Completer<AuthUser?>();
      final l10n = await AppLocalizations.delegate.load(Locale(code));
      await pumpApp(
        tester,
        storage: MemoryLocaleStorage(code),
        auth: FakeAuthRepository(restoreHandler: () => pending.future),
        settle: false,
      );
      await tester.pump();
      await tester.pump();
      expect(find.text(l10n.splashTagline), findsOneWidget);
      pending.complete(null);
      await tester.pumpAndSettle();
    });

    testWidgets(
      '$code localizes pantry edit, interpolation, update and delete errors',
      (tester) async {
        final l10n = await AppLocalizations.delegate.load(Locale(code));
        final pantry = _PantryRepository()..items = [_item];
        await pumpApp(
          tester,
          storage: MemoryLocaleStorage(code),
          auth: FakeAuthRepository(restoreHandler: () async => testAuthUser),
          pantry: pantry,
        );
        await tap(tester, 'pantry-card');
        expect(
          find.text(l10n.quantityWithExpiry('250.5', '2026-10-01')),
          findsOneWidget,
        );
        expect(find.text('Server Oats'), findsOneWidget);
        await tap(tester, 'pantry-item-pantry-1');
        expect(find.text(l10n.editIngredient), findsOneWidget);
        await tap(tester, 'edit-pantry-save-button');
        expect(find.text(l10n.pantryUpdateError), findsOneWidget);
        await tap(tester, 'edit-pantry-delete-button');
        expect(
          find.text(l10n.deletePantryConfirmation('Server Oats')),
          findsOneWidget,
        );
        expect(find.text(l10n.cancel), findsOneWidget);
        await tap(tester, 'edit-pantry-delete-confirm-button');
        expect(find.text(l10n.pantryDeleteError), findsOneWidget);
        expect(find.text(l10n.pantryUpdateError), findsNothing);
      },
    );
  }

  testWidgets(
    'visible pantry error and snackbar retranslate after locale change',
    (tester) async {
      final pantry = _PantryRepository()..listFailure = true;
      final container = await pumpApp(
        tester,
        auth: FakeAuthRepository(restoreHandler: () async => testAuthUser),
        pantry: pantry,
      );
      await tap(tester, 'ai-recipe-card');
      await changeLocale(tester, container, 'uk');
      final uk = await AppLocalizations.delegate.load(const Locale('uk'));
      expect(find.text(uk.featureComingSoon(uk.aiRecipe)), findsOneWidget);
      await tester.pump(const Duration(seconds: 5));
      await tester.pumpAndSettle();
      await tap(tester, 'pantry-card');
      expect(find.text(uk.pantryLoadError), findsOneWidget);
      await changeLocale(tester, container, 'sk');
      final sk = await AppLocalizations.delegate.load(const Locale('sk'));
      expect(find.text(sk.pantryLoadError), findsOneWidget);
      pantry.listFailure = false;
      await tap(tester, 'pantry-retry-button');
      expect(find.text(sk.pantryEmpty), findsOneWidget);
    },
  );

  testWidgets('unsupported system language falls back to English', (
    tester,
  ) async {
    tester.binding.platformDispatcher.localesTestValue = [
      const Locale('de', 'DE'),
    ];
    addTearDown(tester.binding.platformDispatcher.clearLocalesTestValue);
    await pumpApp(tester);
    expect(find.text('Welcome to Mealio'), findsOneWidget);
    expect(
      Localizations.localeOf(
        tester.element(find.byKey(const Key('login-screen'))),
      ),
      const Locale('en'),
    );
  });

  testWidgets('system locale list chooses the first supported language', (
    tester,
  ) async {
    tester.binding.platformDispatcher.localesTestValue = [
      const Locale('de'),
      const Locale('uk', 'UA'),
      const Locale('ru'),
    ];
    addTearDown(tester.binding.platformDispatcher.clearLocalesTestValue);
    await pumpApp(tester);
    expect(find.text('Вітаємо в Mealio'), findsOneWidget);
  });

  testWidgets(
    'login selector changes immediately, keeps fields and errors, returns to system',
    (tester) async {
      tester.binding.platformDispatcher.localesTestValue = [const Locale('sk')];
      addTearDown(tester.binding.platformDispatcher.clearLocalesTestValue);
      final storage = MemoryLocaleStorage();
      final container = await pumpApp(tester, storage: storage);
      final router = container.read(appRouterProvider);
      await tester.enterText(
        find.byKey(const Key('login-email-field')),
        'invalid-email',
      );
      await tester.enterText(
        find.byKey(const Key('login-password-field')),
        '  synthetic password  ',
      );
      await tap(tester, 'login-button');
      await tap(tester, 'language-button');
      await tester.tap(
        find.widgetWithText(CheckedPopupMenuItem<String>, 'Русский'),
      );
      await tester.pumpAndSettle();
      expect(find.text('Добро пожаловать в Mealio'), findsOneWidget);
      expect(find.text('Введите корректный email.'), findsOneWidget);
      expect(find.text('invalid-email'), findsOneWidget);
      final field = tester.widget<TextFormField>(
        find.byKey(const Key('login-password-field')),
      );
      expect(field.controller!.text, '  synthetic password  ');
      expect(container.read(appRouterProvider), same(router));
      expect(storage.value, 'ru');
      await tap(tester, 'language-button');
      await tester.tap(
        find.widgetWithText(CheckedPopupMenuItem<String>, 'Язык системы'),
      );
      await tester.pumpAndSettle();
      expect(find.text('Vitajte v Mealio'), findsOneWidget);
      expect(storage.value, isNull);
      tester.binding.platformDispatcher.localesTestValue = [const Locale('uk')];
      await tester.pumpAndSettle();
      expect(find.text('Вітаємо в Mealio'), findsOneWidget);
      expect(find.text('Введіть коректний email.'), findsOneWidget);
    },
  );

  testWidgets(
    'locale rebuild preserves router, back stack and registration form state',
    (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final container = await pumpApp(tester);
      final router = container.read(appRouterProvider);
      await tap(tester, 'open-register-button');
      await tester.enterText(
        find.byKey(const Key('register-full-name-field')),
        'Test Name',
      );
      await tester.enterText(
        find.byKey(const Key('register-password-field')),
        ' short ',
      );
      await tap(tester, 'register-button');
      await changeLocale(tester, container, 'uk');
      expect(container.read(appRouterProvider), same(router));
      expect(router.state.uri.path, '/register');
      expect(router.canPop(), isTrue);
      expect(find.text('Test Name'), findsOneWidget);
      expect(
        find.text('Пароль має містити щонайменше 15 символів.'),
        findsOneWidget,
      );
      expect(
        tester
            .widget<TextFormField>(
              find.byKey(const Key('register-password-field')),
            )
            .controller!
            .text,
        ' short ',
      );
      await tap(tester, 'register-back-button');
      expect(router.state.uri.path, '/login');
      expect(find.text('Вітаємо в Mealio'), findsOneWidget);
    },
  );

  testWidgets(
    'write failure keeps selected language and reports a localized message',
    (tester) async {
      final storage = MemoryLocaleStorage()..failWrite = true;
      await pumpApp(tester, storage: storage);
      await tap(tester, 'language-button');
      await tester.tap(
        find.widgetWithText(CheckedPopupMenuItem<String>, 'Українська'),
      );
      await tester.pumpAndSettle();
      final l10n = await AppLocalizations.delegate.load(const Locale('uk'));
      expect(find.text(l10n.welcome), findsOneWidget);
      expect(find.text(l10n.languageSaveFailed), findsOneWidget);
    },
  );

  testWidgets(
    'home selector persists through logout without changing auth state on switch',
    (tester) async {
      final auth = FakeAuthRepository(restoreHandler: () async => testAuthUser);
      final storage = MemoryLocaleStorage();
      final container = await pumpApp(tester, storage: storage, auth: auth);
      final router = container.read(appRouterProvider);
      await tap(tester, 'language-button');
      await tester.tap(
        find.widgetWithText(CheckedPopupMenuItem<String>, 'Slovenčina'),
      );
      await tester.pumpAndSettle();
      expect(find.text('Zásoby'), findsOneWidget);
      expect(auth.restoreCalls, 1);
      expect(auth.logoutCalls, 0);
      expect(container.read(appRouterProvider), same(router));
      await tap(tester, 'home-logout-button');
      expect(find.text('Vitajte v Mealio'), findsOneWidget);
      expect(storage.value, 'sk');
    },
  );

  testWidgets('pantry draft and delete dialog survive a locale change', (
    tester,
  ) async {
    final pantry = _PantryRepository()..items = [_item];
    final container = await pumpApp(
      tester,
      auth: FakeAuthRepository(restoreHandler: () async => testAuthUser),
      pantry: pantry,
    );
    final router = container.read(appRouterProvider);
    await tap(tester, 'pantry-card');
    await tap(tester, 'pantry-item-pantry-1');
    await tester.enterText(
      find.byKey(const Key('edit-pantry-quantity-field')),
      '123,45',
    );
    await tap(tester, 'edit-pantry-delete-button');
    await changeLocale(tester, container, 'ru');
    expect(find.text('Удалить Server Oats из запасов?'), findsOneWidget);
    await tap(tester, 'edit-pantry-delete-cancel-button');
    expect(
      tester
          .widget<TextFormField>(
            find.byKey(const Key('edit-pantry-quantity-field')),
          )
          .controller!
          .text,
      '123,45',
    );
    expect(find.text('2026-10-01'), findsOneWidget);
    expect(container.read(appRouterProvider), same(router));
    expect(router.state.uri.path, '/pantry/pantry-1/edit');
  });

  testWidgets(
    'verification success and OTP input retranslate without another request',
    (tester) async {
      final auth = FakeAuthRepository();
      final container = await pumpApp(tester, auth: auth);
      container
          .read(appRouterProvider)
          .go('/verify-email', extra: 'test@example.com');
      await tester.pumpAndSettle();
      await tap(tester, 'verify-email-use-code-button');
      await tap(tester, 'verify-email-otp-request-button');
      await tester.enterText(
        find.byKey(const Key('verify-email-otp-field')),
        '001234',
      );
      await changeLocale(tester, container, 'sk');
      expect(
        find.text('Ak je overenie potrebné, kód bol odoslaný.'),
        findsOneWidget,
      );
      expect(find.text('001234'), findsOneWidget);
      expect(auth.requestEmailVerificationOtpCalls, 1);
      await tap(tester, 'verify-email-otp-confirm-button');
      expect(auth.lastVerificationOtpCode, '001234');
      expect(find.text('E-mail bol overený'), findsOneWidget);
    },
  );

  testWidgets('password recovery success and reset failures retranslate', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(800, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = await pumpApp(tester);
    final router = container.read(appRouterProvider);
    await tap(tester, 'forgot-password-button');
    await tester.enterText(
      find.byKey(const Key('forgot-password-email-field')),
      'test@example.com',
    );
    await tap(tester, 'forgot-password-link-button');
    await changeLocale(tester, container, 'ru');
    final l10n = await AppLocalizations.delegate.load(const Locale('ru'));
    expect(find.text(l10n.resetInstructionsSent), findsOneWidget);
    router.go('/reset-password');
    await tester.pumpAndSettle();
    expect(find.text(l10n.authPasswordResetInvalid), findsOneWidget);
    router.go('/reset-password/code', extra: 'test@example.com');
    await tester.pumpAndSettle();
    await tap(tester, 'password-reset-otp-submit-button');
    expect(find.text(l10n.otpInvalidInput), findsOneWidget);
    await changeLocale(tester, container, 'uk');
    final uk = await AppLocalizations.delegate.load(const Locale('uk'));
    expect(find.text(uk.otpInvalidInput), findsOneWidget);
  });
}

final _ingredient = Ingredient(
  id: 'ingredient-1',
  name: 'Server Oats',
  category: null,
  createdAt: DateTime.utc(2026),
  nutritionValue: null,
);
final _item = PantryItem(
  id: 'pantry-1',
  userId: 'user-1',
  ingredientId: _ingredient.id,
  quantityG: 250.5,
  expiresAt: DateTime.utc(2026, 10, 1),
  createdAt: DateTime.utc(2026),
  updatedAt: DateTime.utc(2026),
  ingredient: _ingredient,
);

class _PantryRepository implements PantryRepository {
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
  List<PantryItem> items = [];
  bool searchFailure = false;
  bool listFailure = false;
  List<Ingredient> ingredients = [];
  String? lastQuantity;

  @override
  Future<List<PantryItem>> getPantry() async {
    if (listFailure) throw PantryFailure.backend();
    return items;
  }

  @override
  Future<List<Ingredient>> searchIngredients({String? search}) async {
    if (searchFailure) throw PantryFailure.searchBackend();
    return ingredients;
  }

  @override
  Future<PantryItem> addPantryItem({
    required String ingredientId,
    required String quantityG,
    DateTime? expiresAt,
  }) async {
    lastQuantity = quantityG;
    throw PantryFailure.createBackend();
  }

  @override
  Future<PantryItem> updatePantryItem({
    required String pantryItemId,
    required String quantityG,
    DateTime? expiresAt,
  }) async => throw PantryFailure.updateBackend();

  @override
  Future<void> deletePantryItem({required String pantryItemId}) async =>
      throw PantryFailure.deleteBackend();
}
