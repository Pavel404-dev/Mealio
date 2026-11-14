import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/storage/secure_storage_provider.dart';
import 'package:mealio/features/auth/data/auth_repository.dart';
import 'package:mealio/features/auth/presentation/auth_controller.dart';
import 'package:mealio/features/recipes/data/recipe_repository.dart';
import 'package:mealio/features/recipes/domain/recipe.dart';
import 'package:mealio/features/recipes/domain/recipe_detail.dart';
import 'package:mealio/features/recipes/domain/recipe_failure.dart';
import 'package:mealio/features/recipes/presentation/recipe_detail_screen.dart';
import 'package:mealio/features/recipes/presentation/recipe_localization.dart';
import 'package:mealio/l10n/generated/app_localizations.dart';

import '../../../helpers/auth_test_fakes.dart';
import '../../../helpers/recipe_test_fakes.dart';

void main() {
  late FakeRecipeRepository repository;
  setUp(() => repository = FakeRecipeRepository());
  Finder key(String name) => find.byKey(Key(name));

  Future<void> pumpDetail(
    WidgetTester tester, {
    String code = 'en',
    bool settle = true,
  }) async {
    final container = ProviderContainer(
      overrides: [
        recipeRepositoryProvider.overrideWithValue(repository),
        secureStorageServiceProvider.overrideWithValue(
          FakeSecureStorageService(),
        ),
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
          home: const RecipeDetailScreen(recipeId: 'recipe-1'),
        ),
      ),
    );
    if (settle) await tester.pumpAndSettle();
  }

  Future<void> reveal(WidgetTester tester, Finder finder) async {
    await tester.scrollUntilVisible(finder, 200, maxScrolls: 80);
    await tester.pumpAndSettle();
  }

  testWidgets(
    'loading waits for all resolved names; retry is disabled while pending',
    (tester) async {
      final response = Completer<RecipeDetail>();
      repository.detailHandler = (_) => response.future;
      await pumpDetail(tester, settle: false);
      await tester.pump();
      expect(key('recipe-detail-loading'), findsOneWidget);
      expect(key('recipe-detail-content'), findsNothing);
      expect(key('recipe-detail-retry'), findsNothing);
      response.complete(recipeDetailFixture());
      await tester.pumpAndSettle();
      expect(key('recipe-detail-content'), findsOneWidget);
      expect(repository.detailCalls, hasLength(1));
    },
  );

  for (final code in ['en', 'ru', 'uk', 'sk']) {
    testWidgets('$code shows exact names/grams/instructions and whole totals', (
      tester,
    ) async {
      final l10n = await AppLocalizations.delegate.load(Locale(code));
      repository.detailHandler = (_) => RecipeDetail(
        recipe: Recipe.fromJson(recipeJson()..['total_protein_g'] = null),
        ingredientNames: {'ingredient-1': 'Имя {server}'},
      );
      await pumpDetail(tester, code: code);
      expect(find.text('Saved recipe'), findsOneWidget);
      expect(find.text('A saved recipe description'), findsOneWidget);
      expect(find.text(l10n.recipeServings(4)), findsOneWidget);
      expect(find.text(l10n.recipeWholeNutrition), findsOneWidget);
      expect(find.text(l10n.recipeCalories('330')), findsOneWidget);
      expect(
        find.text(l10n.recipeProtein(l10n.recipeNoNutrition)),
        findsOneWidget,
      );
      expect(find.text(l10n.recipeCarbs('0')), findsOneWidget);
      await reveal(tester, find.text('Имя {server}'));
      expect(find.text(l10n.quantityGrams('200')), findsOneWidget);
      await reveal(tester, key('recipe-detail-instructions'));
      expect(find.text(l10n.recipeInstructions), findsOneWidget);
      expect(find.text('First step.\nSecond step.'), findsOneWidget);
    });

    testWidgets(
      '$code empty composition is successful and keeps instructions',
      (tester) async {
        final l10n = await AppLocalizations.delegate.load(Locale(code));
        repository.detailHandler = (_) => RecipeDetail(
          recipe: Recipe.fromJson(
            recipeJson()
              ..['description'] = null
              ..['recipe_ingredients'] = [],
          ),
          ingredientNames: {},
        );
        await pumpDetail(tester, code: code);
        await reveal(tester, key('recipe-detail-empty-ingredients'));
        expect(find.text(l10n.recipeNoIngredients), findsOneWidget);
        await reveal(tester, key('recipe-detail-instructions'));
        expect(find.text('First step.\nSecond step.'), findsOneWidget);
        expect(key('recipe-detail-error'), findsNothing);
      },
    );

    testWidgets('$code errors have safe localized context and retry rereads', (
      tester,
    ) async {
      final l10n = await AppLocalizations.delegate.load(Locale(code));
      for (final type in RecipeFailureType.values) {
        repository.detailHandler = (_) => throw RecipeFailure(type);
        await pumpDetail(tester, code: code);
        expect(
          find.text(RecipeFailure(type).localized(l10n, detail: true)),
          findsOneWidget,
        );
        expect(key('recipe-detail-content'), findsNothing);
      }
      repository.detailHandler = (_) =>
          throw StateError('synthetic-private-detail');
      await pumpDetail(tester, code: code);
      expect(find.text(l10n.recipeDetailLoadError), findsOneWidget);
      expect(find.textContaining('synthetic-private-detail'), findsNothing);
      expect(l10n.recipeUnavailable, isNot(l10n.recipeIngredientUnavailable));
      final before = repository.detailCalls.length;
      final response = Completer<RecipeDetail>();
      repository.detailHandler = (_) => response.future;
      await tester.tap(key('recipe-detail-retry'));
      await tester.tap(key('recipe-detail-retry'));
      await tester.pump();
      expect(key('recipe-detail-loading'), findsOneWidget);
      expect(repository.detailCalls.length, before + 1);
      response.complete(recipeDetailFixture(title: 'Fresh detail'));
      await tester.pumpAndSettle();
      expect(find.text('Fresh detail'), findsOneWidget);
    });

    testWidgets(
      '$code long text and error/empty actions fit 320px at scale 2',
      (tester) async {
        tester.view.physicalSize = const Size(320, 568);
        tester.view.devicePixelRatio = 1;
        tester.platformDispatcher.textScaleFactorTestValue = 2;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        final title = List.filled(255, 'Я').join();
        final name = List.filled(255, 'Ы').join();
        final instructions =
            '${List.filled(40, 'Длинный шаг {server}\n').join()}Последний шаг';
        final json = recipeJson(title: title)..['instructions'] = instructions;
        (json['recipe_ingredients'] as List).single['quantity_g'] = '12.25';
        repository.detailHandler = (_) => RecipeDetail(
          recipe: Recipe.fromJson(json),
          ingredientNames: {'ingredient-1': name},
        );
        await pumpDetail(tester, code: code);
        expect(find.text(title), findsOneWidget);
        await reveal(tester, find.text(name));
        final l10n = await AppLocalizations.delegate.load(Locale(code));
        await reveal(
          tester,
          find.text(l10n.quantityGrams(code == 'en' ? '12.25' : '12,25')),
        );
        await reveal(tester, key('recipe-detail-instructions'));
        expect(
          tester.widget<Text>(key('recipe-detail-instructions')).data,
          instructions,
        );
        await tester.drag(find.byType(ListView), const Offset(0, -5000));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        repository.detailHandler = (_) =>
            throw const RecipeFailure(RecipeFailureType.ingredientUnavailable);
        await pumpDetail(tester, code: code);
        await reveal(tester, key('recipe-detail-retry'));
        expect(tester.takeException(), isNull);
        repository.detailHandler = (_) => RecipeDetail(
          recipe: Recipe.fromJson(recipeJson()..['recipe_ingredients'] = []),
          ingredientNames: {},
        );
        await tester.tap(key('recipe-detail-retry'));
        await tester.pumpAndSettle();
        await reveal(tester, key('recipe-detail-empty-ingredients'));
        expect(tester.takeException(), isNull);
      },
    );
  }
}
