import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/storage/secure_storage_provider.dart';
import 'package:mealio/features/auth/data/auth_repository.dart';
import 'package:mealio/features/auth/presentation/auth_controller.dart';
import 'package:mealio/features/recipes/data/recipe_repository.dart';
import 'package:mealio/features/recipes/domain/recipe.dart';
import 'package:mealio/features/recipes/domain/recipe_failure.dart';
import 'package:mealio/features/recipes/presentation/recipe_localization.dart';
import 'package:mealio/features/recipes/presentation/recipes_screen.dart';
import 'package:mealio/l10n/generated/app_localizations.dart';

import '../../../helpers/auth_test_fakes.dart';
import '../../../helpers/recipe_test_fakes.dart';

void main() {
  late FakeRecipeRepository repository;
  late FakeSecureStorageService storage;
  late ProviderContainer container;

  setUp(() {
    repository = FakeRecipeRepository();
    storage = FakeSecureStorageService();
  });

  Future<void> pumpScreen(
    WidgetTester tester, {
    String code = 'en',
    bool settle = true,
  }) async {
    container = ProviderContainer(
      overrides: [
        recipeRepositoryProvider.overrideWithValue(repository),
        secureStorageServiceProvider.overrideWithValue(storage),
        authRepositoryProvider.overrideWithValue(
          FakeAuthRepository(restoreHandler: () async => testAuthUser),
        ),
      ],
    );
    addTearDown(container.dispose);
    await container.read(authControllerProvider.future);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        key: ValueKey(container),
        container: container,
        child: MaterialApp(
          locale: Locale(code),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: const RecipesScreen(),
        ),
      ),
    );
    if (settle) await tester.pumpAndSettle();
  }

  Finder key(String value) => find.byKey(Key(value));

  Future<void> reveal(WidgetTester tester, String value) async {
    await tester.scrollUntilVisible(key(value), 500, maxScrolls: 70);
    await tester.pumpAndSettle();
  }

  testWidgets('shows loading until the first response resolves', (
    tester,
  ) async {
    final response = Completer<List<Recipe>>();
    repository.handler = (_) => response.future;
    await pumpScreen(tester, settle: false);
    await tester.pump();
    expect(key('recipes-loading'), findsOneWidget);
    expect(key('recipes-empty-state'), findsNothing);
    response.complete([]);
    await tester.pumpAndSettle();
    expect(key('recipes-empty-state'), findsOneWidget);
    expect(repository.calls, hasLength(1));
  });

  testWidgets('shows saved servings and whole-recipe totals without dividing', (
    tester,
  ) async {
    repository.handler = (_) => [Recipe.fromJson(recipeJson())];
    await pumpScreen(tester);
    expect(find.text('Saved recipe'), findsOneWidget);
    expect(find.text('4 servings'), findsOneWidget);
    expect(find.text('Nutrition for the whole recipe'), findsOneWidget);
    expect(find.text('Calories (kcal): 330'), findsOneWidget);
    expect(find.text('Protein (g): 62'), findsOneWidget);
    expect(find.text('Carbs (g): 0'), findsOneWidget);
    expect(find.text('Fat (g): 7.2'), findsOneWidget);
    expect(key('recipes-load-more'), findsNothing);
  });

  testWidgets(
    'rate limit retry preserves first page and appends the 51st recipe once',
    (tester) async {
      repository.handler = (_) => recipePage();
      await pumpScreen(tester);
      await reveal(tester, 'recipes-load-more');
      repository.handler = (_) =>
          throw const RecipeFailure(RecipeFailureType.rateLimited);
      await tester.tap(key('recipes-load-more'));
      await tester.pumpAndSettle();
      expect(key('recipe-recipe-49'), findsOneWidget);
      expect(find.text('Saved recipe 49'), findsOneWidget);
      final l10n = AppLocalizations.of(tester.element(key('recipes-screen')));
      expect(find.text(l10n.rateLimited), findsOneWidget);
      final response = Completer<List<Recipe>>();
      repository.handler = (_) => response.future;
      await reveal(tester, 'recipes-retry');
      await tester.tap(key('recipes-retry'));
      await tester.pump();
      expect(key('recipes-loading'), findsOneWidget);
      expect(key('recipes-retry'), findsNothing);
      expect(key('recipe-recipe-49'), findsOneWidget);
      response.complete(recipePage(start: 50, count: 1));
      await tester.pumpAndSettle();
      await reveal(tester, 'recipe-recipe-50');
      expect(find.text('Saved recipe 50'), findsOneWidget);
      expect(key('recipes-load-more'), findsNothing);
      expect(repository.calls.map((call) => call.offset), [0, 50, 50]);
    },
  );

  for (final code in ['en', 'ru', 'uk', 'sk']) {
    testWidgets(
      '$code renders empty state and recipe null/zero with localized numbers',
      (tester) async {
        final l10n = await AppLocalizations.delegate.load(Locale(code));
        await pumpScreen(tester, code: code);
        expect(find.text(l10n.recipesEmpty), findsOneWidget);
        expect(find.text(l10n.recipesEmptyDescription), findsOneWidget);
        expect(key('recipes-load-more'), findsNothing);
        repository.handler = (_) => [
          Recipe.fromJson(recipeJson()..['total_calories'] = null),
        ];
        await pumpScreen(tester, code: code);
        expect(find.text(l10n.recipeServings(4)), findsOneWidget);
        expect(find.text(l10n.recipeWholeNutrition), findsOneWidget);
        expect(
          find.text(l10n.recipeCalories(l10n.recipeNoNutrition)),
          findsOneWidget,
        );
        expect(find.text(l10n.recipeCarbs('0')), findsOneWidget);
        expect(
          find.text(l10n.recipeFat(code == 'en' ? '7.2' : '7,2')),
          findsOneWidget,
        );
      },
    );

    testWidgets('$code safe failure retries exactly once to success', (
      tester,
    ) async {
      final l10n = await AppLocalizations.delegate.load(Locale(code));
      repository.handler = (_) => throw StateError('synthetic-private-detail');
      await pumpScreen(tester, code: code);
      expect(key('recipes-error-state'), findsOneWidget);
      expect(find.text(l10n.recipesLoadError), findsOneWidget);
      expect(find.textContaining('synthetic-private-detail'), findsNothing);
      expect(repository.calls, hasLength(1));
      repository.handler = (_) => recipePage(count: 1);
      await tester.tap(key('recipes-retry'));
      await tester.pumpAndSettle();
      expect(key('recipes-list'), findsOneWidget);
      expect(repository.calls.map((call) => call.offset), [0, 0]);
    });

    testWidgets(
      '$code long title, large text and status actions fit a 320px screen',
      (tester) async {
        tester.view.physicalSize = const Size(320, 568);
        tester.view.devicePixelRatio = 1;
        tester.platformDispatcher.textScaleFactorTestValue = 2;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        final title = List.filled(255, 'Я').join();
        repository.handler = (_) => [Recipe.fromJson(recipeJson(title: title))];
        await pumpScreen(tester, code: code);
        expect(find.text(title), findsOneWidget);
        final l10n = await AppLocalizations.delegate.load(Locale(code));
        await tester.scrollUntilVisible(
          find.text(l10n.recipeFat(code == 'en' ? '7.2' : '7,2')),
          200,
        );
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        repository.handler = (_) => [];
        await pumpScreen(tester, code: code);
        expect(tester.takeException(), isNull);
        repository.handler = (_) =>
            throw const RecipeFailure(RecipeFailureType.connection);
        await pumpScreen(tester, code: code);
        await reveal(tester, 'recipes-retry');
        expect(find.text(l10n.connectionError), findsOneWidget);
        expect(tester.takeException(), isNull);
        repository.handler = (_) => [];
        await tester.tap(key('recipes-retry'));
        await tester.pumpAndSettle();
        expect(key('recipes-empty-state'), findsOneWidget);
      },
    );

    test('$code maps all failures and generates recipe plurals', () async {
      final l10n = await AppLocalizations.delegate.load(Locale(code));
      for (final type in RecipeFailureType.values) {
        final text = RecipeFailure(type).localized(l10n);
        expect(text, isNotEmpty);
        expect(text, isNot(contains(type.toString())));
      }
      expect(
        const RecipeFailure(RecipeFailureType.authentication).localized(l10n),
        l10n.recipesAuthentication,
      );
      final suffix = switch (code) {
        'ru' || 'uk' => ['порція', 'порції', 'порцій'],
        'sk' => ['porcia', 'porcie', 'porcií'],
        _ => ['serving', 'servings', 'servings'],
      };
      // Russian and Ukrainian differ only in the spelling of the singular here.
      final expected = code == 'ru' ? ['порция', 'порции', 'порций'] : suffix;
      expect(l10n.recipeServings(1), '1 ${expected[0]}');
      expect(l10n.recipeServings(4), '4 ${expected[1]}');
      expect(l10n.recipeServings(12), '12 ${expected[2]}');
    });
  }
}
