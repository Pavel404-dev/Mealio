import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/app/app.dart';
import 'package:mealio/app/router/app_router.dart';
import 'package:mealio/core/auth/auth_token_pair.dart';
import 'package:mealio/core/auth/session_invalidation.dart';
import 'package:mealio/core/localization/locale_controller.dart';
import 'package:mealio/core/storage/secure_storage_provider.dart';
import 'package:mealio/features/auth/data/auth_repository.dart';
import 'package:mealio/features/auth/domain/auth_user.dart';
import 'package:mealio/features/auth/presentation/auth_controller.dart';
import 'package:mealio/features/nutrition/data/nutrition_repository.dart';
import 'package:mealio/features/nutrition/domain/nutrition_failure.dart';
import 'package:mealio/features/nutrition/domain/nutrition_profile.dart';
import 'package:mealio/features/nutrition/domain/nutrition_calculation.dart';
import 'package:mealio/l10n/generated/app_localizations.dart';

import '../../../helpers/auth_test_fakes.dart';
import '../../../helpers/locale_test_fakes.dart';
import '../../../helpers/nutrition_test_fakes.dart';

void main() {
  late FakeNutritionRepository repository;
  late FakeSecureStorageService storage;
  late FakeAuthRepository auth;
  late ProviderContainer container;
  late AuthUser loginUser;

  void configure() {
    repository = FakeNutritionRepository();
    storage = FakeSecureStorageService(
      accessToken: 'synthetic-access',
      refreshToken: 'synthetic-refresh',
    );
    loginUser = testAuthUser;
    auth = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
      currentUserHandler: () async => AuthUser(
        id: testAuthUser.id,
        email: testAuthUser.email,
        fullName: testAuthUser.fullName,
        createdAt: testAuthUser.createdAt,
        updatedAt: testAuthUser.updatedAt,
      ),
      logoutHandler: () => storage.deleteTokenPair(),
      loginHandler: ({required email, required password}) async {
        await storage.writeTokenPair(
          const AuthTokenPair(
            accessToken: 'synthetic-access',
            refreshToken: 'synthetic-refresh',
          ),
        );
        return loginUser;
      },
    );
    container = ProviderContainer(
      overrides: [
        authRepositoryProvider.overrideWithValue(auth),
        secureStorageServiceProvider.overrideWithValue(storage),
        nutritionRepositoryProvider.overrideWithValue(repository),
        localeStorageProvider.overrideWithValue(MemoryLocaleStorage('en')),
      ],
    );
  }

  tearDown(() => container.dispose());

  Finder key(String name) => find.byKey(Key(name));

  Future<void> start(WidgetTester tester) async {
    await tester.pumpWidget(
      UncontrolledProviderScope(container: container, child: const MealioApp()),
    );
    await tester.pumpAndSettle();
    expect(key('home-screen'), findsOneWidget);
  }

  Future<void> tap(WidgetTester tester, String name) async {
    await tester.scrollUntilVisible(
      key(name),
      150,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();
    await tester.tap(key(name));
    await tester.pumpAndSettle();
  }

  Future<void> open(WidgetTester tester) async {
    await tap(tester, 'nutrition-setup-card');
    expect(key('nutrition-setup-screen'), findsOneWidget);
  }

  void select(WidgetTester tester, NutritionField field, String value) {
    tester
        .widget<DropdownButtonFormField<String>>(
          key('nutrition-${field.wireName}'),
        )
        .onChanged!(value);
  }

  Future<void> body(WidgetTester tester) async {
    select(tester, NutritionField.sex, 'female');
    await tester.enterText(key('nutrition-birth_date'), '2000-02-29');
    await tester.enterText(key('nutrition-height_cm'), '193,0');
    await tester.ensureVisible(key('nutrition-weight_kg'));
    await tester.enterText(key('nutrition-weight_kg'), '78,40');
  }

  String text(WidgetTester tester, String field) =>
      tester.widget<TextFormField>(key('nutrition-$field')).controller?.text ??
      tester.widget<TextFormField>(key('nutrition-$field')).initialValue!;

  testWidgets(
    'Home entry GET, required fields, save, system Back, exit warning and reopen',
    (tester) async {
      configure();
      await start(tester);
      await open(tester);
      expect(repository.loads, 1);
      expect(repository.saves, isEmpty);
      expect(find.text('Step 1 of 6'), findsOneWidget);
      // Exercise the actual dropdown menu and accessible label.
      await tester.tap(key('nutrition-goal'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Gain weight').last);
      await tester.pumpAndSettle();
      await tap(tester, 'nutrition-save');
      expect(repository.saves.single, {NutritionField.goal: 'gain_weight'});
      await tap(tester, 'nutrition-save');
      expect(repository.saves, hasLength(1));
      expect(find.text('This field is required.'), findsWidgets);
      await tester.drag(find.byType(ListView), const Offset(0, 1000));
      await tester.pumpAndSettle();
      await body(tester);
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(find.text('Step 1 of 6'), findsOneWidget);
      await tap(tester, 'nutrition-save');
      expect(text(tester, 'height_cm'), '193,0');
      await tap(tester, 'nutrition-save');
      expect(repository.saves.last[NutritionField.weight], '78.40');
      select(tester, NutritionField.activity, 'extra_active');
      await tester.pump();
      await tap(tester, 'nutrition-exit');
      expect(find.text('Leave without saving your edits?'), findsOneWidget);
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(key('nutrition-stay'), findsNothing);
      await tap(tester, 'nutrition-exit');
      await tap(tester, 'nutrition-stay');
      expect(
        tester
            .widget<DropdownButtonFormField<String>>(
              key('nutrition-activity_level'),
            )
            .initialValue,
        'extra_active',
      );
      await tap(tester, 'nutrition-exit');
      await tap(tester, 'nutrition-discard');
      expect(key('home-screen'), findsOneWidget);
      await open(tester);
      expect(find.text('Step 1 of 6'), findsOneWidget);
      await tap(tester, 'nutrition-save');
      expect(text(tester, 'weight_kg'), '78.40');
      await tap(tester, 'nutrition-save');
      expect(
        tester
            .widget<DropdownButtonFormField<String>>(
              key('nutrition-activity_level'),
            )
            .initialValue,
        isNull,
      );
      expect(repository.loads, 2);
      expect(repository.saves, hasLength(2));
    },
  );

  testWidgets(
    'last Save confirms once then returns Home; no-change steps never PATCH',
    (tester) async {
      configure();
      repository.json.addAll(nutritionJson(full: true));
      await start(tester);
      await open(tester);
      final firstButton = tester.widget<FilledButton>(key('nutrition-save'));
      firstButton.onPressed!();
      firstButton.onPressed!();
      await tester.pumpAndSettle();
      expect(find.text('Step 2 of 6'), findsOneWidget);
      await tap(tester, 'nutrition-save');
      select(tester, NutritionField.activity, 'very_active');
      await tester.pump();
      final pending = Completer<NutritionProfile>();
      repository.saveHandler = (_) => pending.future;
      final button = tester.widget<FilledButton>(key('nutrition-save'));
      button.onPressed!();
      button.onPressed!();
      await tester.pump();
      expect(repository.saves, hasLength(1));
      expect(find.text('Step 3 of 6'), findsOneWidget);
      await tester.binding.handlePopRoute();
      await tester.pump();
      expect(key('nutrition-setup-screen'), findsOneWidget);
      expect(
        tester.widget<IconButton>(key('nutrition-back')).onPressed,
        isNull,
      );
      pending.complete(
        NutritionProfile.fromJson(
          nutritionJson(full: true)..['activity_level'] = 'very_active',
        ),
      );
      await tester.pumpAndSettle();
      await tap(tester, 'nutrition-save');
      await tap(tester, 'nutrition-save');
      await tap(tester, 'nutrition-save');
      expect(key('home-screen'), findsOneWidget);
      expect(find.text('Profile saved.'), findsNothing);
    },
  );

  testWidgets(
    'initial loading, safe error and retry; Back exits clean first step',
    (tester) async {
      configure();
      final pending = Completer<NutritionProfile>();
      repository.loadHandler = () => pending.future;
      await start(tester);
      await tester.tap(key('nutrition-setup-card'));
      await tester.pump();
      expect(repository.loads, 1);
      // Finish only the route transition; the GET remains held by a barrier.
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.text('Loading profile…'), findsOneWidget);
      expect(key('nutrition-save'), findsNothing);
      pending.completeError(StateError('synthetic-private-detail'));
      await tester.pumpAndSettle();
      expect(key('nutrition-error'), findsOneWidget);
      expect(find.textContaining('synthetic-private-detail'), findsNothing);
      repository.loadHandler = null;
      await tap(tester, 'nutrition-retry');
      expect(repository.loads, 2);
      await tester.binding.handlePopRoute();
      await tester.pumpAndSettle();
      expect(key('home-screen'), findsOneWidget);
      expect(repository.saves, isEmpty);
    },
  );

  testWidgets(
    'save timeout retains current step and input; retry is explicit',
    (tester) async {
      configure();
      await start(tester);
      await open(tester);
      await tap(tester, 'nutrition-save');
      await body(tester);
      repository.saveHandler = (_) =>
          Future.error(const NutritionFailure(NutritionFailureType.connection));
      await tap(tester, 'nutrition-save');
      expect(repository.saves, hasLength(1));
      await tester.drag(find.byType(ListView), const Offset(0, 1000));
      await tester.pumpAndSettle();
      expect(text(tester, 'weight_kg'), '78,40');
      expect(find.text('Step 2 of 6'), findsOneWidget);
      repository.saveHandler = null;
      await tap(tester, 'nutrition-save');
      expect(repository.saves, hasLength(2));
      expect(repository.saves[0], repository.saves[1]);
      expect(find.text('Step 3 of 6'), findsOneWidget);
    },
  );

  testWidgets(
    'logout/new login discards unsaved edits and reloads saved profile at step 1',
    (tester) async {
      configure();
      await start(tester);
      await open(tester);
      select(tester, NutritionField.goal, 'gain_weight');
      await tap(tester, 'nutrition-save');
      await body(tester);
      final controller = container.read(authControllerProvider.notifier);
      await controller.logout();
      await tester.pumpAndSettle();
      expect(key('login-screen'), findsOneWidget);
      await controller.login(
        email: 'synthetic@example.com',
        password: 'synthetic-password',
      );
      await tester.pumpAndSettle();
      await open(tester);
      expect(find.text('Step 1 of 6'), findsOneWidget);
      expect(
        tester
            .widget<DropdownButtonFormField<String>>(key('nutrition-goal'))
            .initialValue,
        'gain_weight',
      );
      await tap(tester, 'nutrition-save');
      expect(text(tester, 'height_cm'), isEmpty);
      expect(text(tester, 'birth_date'), isEmpty);
    },
  );

  for (final sameUser in [false, true]) {
    for (final save in [false, true]) {
      for (final fail in [false, true]) {
        testWidgets(
          'late ${save ? 'last Save' : 'GET'} ${fail ? 'failure' : 'success'} cannot navigate or publish after ${sameUser ? 'A→A' : 'A→B'}',
          (tester) async {
            configure();
            repository.json.addAll(nutritionJson(full: true));
            final pending = Completer<NutritionProfile>();
            await start(tester);
            if (save) {
              await open(tester);
              await tap(tester, 'nutrition-save');
              await tap(tester, 'nutrition-save');
              select(tester, NutritionField.activity, 'extra_active');
              await tester.pump();
              repository.saveHandler = (_) => pending.future;
              tester.widget<FilledButton>(key('nutrition-save')).onPressed!();
              await tester.pump();
              expect(repository.saves, hasLength(1));
            } else {
              repository.loadHandler = () => pending.future;
              await tester.tap(key('nutrition-setup-card'));
              await tester.pump();
              expect(repository.loads, 1);
            }
            final authController = container.read(
              authControllerProvider.notifier,
            );
            await authController.logout();
            await tester.pumpAndSettle();
            repository.loadHandler = null;
            repository.saveHandler = null;
            if (!sameUser) {
              loginUser = AuthUser(
                id: 'synthetic-user-b',
                email: 'synthetic-b@example.com',
                fullName: null,
                createdAt: DateTime.utc(2026),
                updatedAt: DateTime.utc(2026),
              );
            }
            await authController.login(
              email: 'synthetic@example.com',
              password: 'synthetic-password',
            );
            await tester.pumpAndSettle();
            await open(tester);
            select(tester, NutritionField.goal, 'lose_weight');
            await tester.pump();
            if (fail) {
              pending.completeError(
                const NutritionFailure(NutritionFailureType.connection),
              );
            } else {
              pending.complete(
                NutritionProfile.fromJson(nutritionJson(full: true)),
              );
            }
            await tester.pumpAndSettle();
            expect(key('nutrition-setup-screen'), findsOneWidget);
            expect(find.text('Step 1 of 6'), findsOneWidget);
            expect(
              tester
                  .widget<DropdownButtonFormField<String>>(
                    key('nutrition-goal'),
                  )
                  .initialValue,
              'lose_weight',
            );
            expect(key('nutrition-error'), findsNothing);
            expect(find.text('Profile saved.'), findsNothing);
            expect(tester.takeException(), isNull);
          },
        );
      }
    }
  }

  testWidgets(
    'same-lifetime user reload/refresh and locale changes keep dirty inputs and errors',
    (tester) async {
      configure();
      await start(tester);
      await open(tester);
      await tap(tester, 'nutrition-save');
      await body(tester);
      await tester.enterText(key('nutrition-weight_kg'), '78,400');
      await tap(tester, 'nutrition-save');
      await storage.replaceTokenPairIfRefreshTokenMatches(
        expectedRefreshToken: 'synthetic-refresh',
        pair: const AuthTokenPair(
          accessToken: 'synthetic-rotated',
          refreshToken: 'synthetic-rotated-refresh',
        ),
      );
      await container.read(authControllerProvider.notifier).reloadCurrentUser();
      for (final code in ['ru', 'uk', 'sk', 'en']) {
        await container
            .read(localeControllerProvider.notifier)
            .setLocale(Locale(code));
        await tester.pumpAndSettle();
        final context = tester.element(key('nutrition-setup-screen'));
        final l10n = AppLocalizations.of(context);
        expect(find.text(l10n.nutritionWeightInvalid), findsOneWidget);
        expect(text(tester, 'weight_kg'), '78,400');
        expect(repository.loads, 1);
      }
      await tester.enterText(key('nutrition-weight_kg'), '78,40');
      repository.saveHandler = (_) => Future.error(
        const NutritionFailure(NutritionFailureType.rateLimited),
      );
      await tap(tester, 'nutrition-save');
      await container
          .read(localeControllerProvider.notifier)
          .setLocale(const Locale('ru'));
      await tester.pumpAndSettle();
      final l10n = AppLocalizations.of(
        tester.element(key('nutrition-setup-screen')),
      );
      expect(find.text(l10n.rateLimited), findsOneWidget);
      expect(text(tester, 'weight_kg'), '78,40');
    },
  );

  for (final code in ['en', 'ru', 'uk', 'sk']) {
    testWidgets(
      '$code small screen large text, keyboard and all steps remain usable',
      (tester) async {
        configure();
        repository.json.addAll(nutritionJson(full: true));
        await start(tester);
        tester.view.physicalSize = const Size(320, 568);
        tester.view.devicePixelRatio = 1;
        tester.platformDispatcher.textScaleFactorTestValue = 2;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        await container
            .read(localeControllerProvider.notifier)
            .setLocale(Locale(code));
        await tester.pumpAndSettle();
        await open(tester);
        await tap(tester, 'nutrition-save');
        await tester.scrollUntilVisible(
          key('nutrition-height_cm'),
          100,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.enterText(key('nutrition-height_cm'), '193,0');
        tester.view.viewInsets = const FakeViewPadding(bottom: 180);
        addTearDown(tester.view.resetViewInsets);
        await tester.pump();
        await tap(tester, 'nutrition-save');
        tester.view.resetViewInsets();
        await tester.pump();
        await tester.drag(find.byType(ListView), const Offset(0, 1000));
        await tester.pumpAndSettle();
        await tester.scrollUntilVisible(
          key('nutrition-activity_level'),
          100,
          scrollable: find.byType(Scrollable).first,
        );
        select(tester, NutritionField.activity, 'extra_active');
        await tester.pump();
        await tap(tester, 'nutrition-exit');
        await tap(tester, 'nutrition-stay');
        await tap(tester, 'nutrition-save');
        await tap(tester, 'nutrition-save');
        await tap(tester, 'nutrition-save');
        await tap(tester, 'nutrition-calculate');
        await tap(tester, 'nutrition-save');
        expect(key('home-screen'), findsOneWidget);
        expect(tester.takeException(), isNull);
      },
    );
  }

  testWidgets(
    'direct protected route cannot load profile unauthenticated; login still Home',
    (tester) async {
      configure();
      auth.restoreHandler = () async => null;
      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: const MealioApp(),
        ),
      );
      await tester.pumpAndSettle();
      container.read(appRouterProvider).go('/nutrition/setup');
      await tester.pumpAndSettle();
      expect(key('login-screen'), findsOneWidget);
      expect(repository.loads, 0);
      await container
          .read(authControllerProvider.notifier)
          .login(
            email: 'synthetic@example.com',
            password: 'synthetic-password',
          );
      await tester.pumpAndSettle();
      expect(key('home-screen'), findsOneWidget);
      expect(repository.loads, 0);
      container.read(appRouterProvider).go('/nutrition/setup');
      await tester.pumpAndSettle();
      expect(repository.loads, 1);
      await tester.tap(key('nutrition-back'));
      await tester.pumpAndSettle();
      expect(key('home-screen'), findsOneWidget);
    },
  );

  testWidgets(
    'protected setup waits for auth initialization and does not force onboarding',
    (tester) async {
      configure();
      final restore = Completer<AuthUser?>();
      auth.restoreHandler = () => restore.future;
      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: const MealioApp(),
        ),
      );
      container.read(appRouterProvider).go('/nutrition/setup');
      await tester.pump();
      expect(key('splash-screen'), findsOneWidget);
      expect(repository.loads, 0);
      restore.complete(testAuthUser);
      await tester.pumpAndSettle();
      expect(key('home-screen'), findsOneWidget);
      expect(repository.loads, 0);
    },
  );

  testWidgets(
    'session invalidation removes dirty input without exit confirmation',
    (tester) async {
      configure();
      await start(tester);
      await open(tester);
      select(tester, NutritionField.goal, 'gain_weight');
      await tester.pump();
      auth.restoreHandler = () async => null;
      await storage.deleteTokenPair();
      container.read(sessionInvalidationProvider.notifier).invalidate();
      await tester.pumpAndSettle();
      expect(key('login-screen'), findsOneWidget);
      expect(key('nutrition-stay'), findsNothing);
      expect(repository.saves, isEmpty);
    },
  );

  testWidgets(
    'fresh app instance restores saved profile but not an unsaved draft',
    (tester) async {
      configure();
      await start(tester);
      await open(tester);
      select(tester, NutritionField.goal, 'gain_weight');
      await tap(tester, 'nutrition-save');
      await body(tester);
      final savedServer = Map<String, dynamic>.of(repository.json);
      await tester.pumpWidget(const SizedBox.shrink());
      container.dispose();
      configure();
      repository.json.addAll(savedServer);
      await start(tester);
      await open(tester);
      expect(find.text('Step 1 of 6'), findsOneWidget);
      expect(
        tester
            .widget<DropdownButtonFormField<String>>(key('nutrition-goal'))
            .initialValue,
        'gain_weight',
      );
      await tap(tester, 'nutrition-save');
      expect(text(tester, 'birth_date'), isEmpty);
      expect(text(tester, 'weight_kg'), isEmpty);
      expect(repository.saves, isEmpty);
    },
  );
  Future<void> summary(WidgetTester tester) async {
    await open(tester);
    for (var i = 0; i < 5; i++) {
      await tap(tester, 'nutrition-save');
    }
  }

  for (final complete in [false, true]) {
    testWidgets(
      'W7 keep ${complete ? 'complete' : 'partial'} targets after calculation exits without save notification',
      (tester) async {
        configure();
        repository.json.addAll(nutritionJson(full: true));
        if (complete) {
          repository.json.addAll({
            'daily_carbs_target_g': 300,
            'daily_fat_target_g': 80,
          });
        }
        await start(tester);
        await summary(tester);
        await tap(tester, 'nutrition-calculate');
        expect(find.text('Calories (kcal/day): 3204'), findsOneWidget);
        await tap(tester, 'nutrition-save');
        expect(key('home-screen'), findsOneWidget);
        expect(repository.patches, isEmpty);
        expect(find.text('Profile saved.'), findsNothing);
      },
    );
  }
  for (final fail in [false, true]) {
    testWidgets(
      'W7 explicit apply notifies only after successful PATCH; failure=$fail',
      (tester) async {
        configure();
        repository.json.addAll(nutritionJson(full: true));
        await start(tester);
        await summary(tester);
        await tap(tester, 'nutrition-calculate');
        await tester.ensureVisible(key('nutrition-select-estimate'));
        tester
            .widget<CheckboxListTile>(key('nutrition-select-estimate'))
            .onChanged!(true);
        await tester.pump();
        final response = Completer<NutritionProfile>();
        repository.saveHandler = (_) => response.future;
        tester.widget<FilledButton>(key('nutrition-save')).onPressed!();
        await tester.pump();
        expect(repository.patches.single, {
          'daily_calories_target': 3204,
          'daily_protein_target_g': 160,
          'daily_carbs_target_g': 400,
          'daily_fat_target_g': 107,
        });
        expect(key('nutrition-setup-screen'), findsOneWidget);
        expect(find.text('Profile saved.'), findsNothing);
        if (fail) {
          response.completeError(
            const NutritionFailure(NutritionFailureType.connection),
          );
        } else {
          response.complete(
            NutritionProfile.fromJson({
              ...repository.json,
              ...repository.patches.single,
            }),
          );
        }
        await tester.pumpAndSettle();
        expect(repository.patches, hasLength(1));
        if (fail) {
          expect(key('nutrition-setup-screen'), findsOneWidget);
          expect(key('nutrition-error'), findsOneWidget);
          expect(find.text('Profile saved.'), findsNothing);
          await tap(tester, 'nutrition-exit');
          expect(key('home-screen'), findsOneWidget);
          expect(find.text('Profile saved.'), findsNothing);
        } else {
          expect(key('home-screen'), findsOneWidget);
          expect(find.text('Profile saved.'), findsOneWidget);
        }
      },
    );
  }

  for (final field in [
    'daily_calories_target',
    'daily_protein_target_g',
    'daily_carbs_target_g',
    'daily_fat_target_g',
  ]) {
    for (final missing in [true, false]) {
      testWidgets(
        'W7 confirm rejects $field ${missing ? 'null' : 'mismatch'} without false success or automatic retry',
        (tester) async {
          configure();
          repository.json.addAll(nutritionJson(full: true));
          await start(tester);
          await summary(tester);
          await tap(tester, 'nutrition-calculate');
          await tester.ensureVisible(key('nutrition-select-estimate'));
          tester
              .widget<CheckboxListTile>(key('nutrition-select-estimate'))
              .onChanged!(true);
          await tester.pump();
          repository.saveHandler = (patch) async => NutritionProfile.fromJson({
            ...repository.json,
            ...patch.json,
            field: missing ? null : (patch.json[field] as int) + 1,
          });
          await tap(tester, 'nutrition-save');
          expect(key('nutrition-setup-screen'), findsOneWidget);
          expect(key('home-screen'), findsNothing);
          expect(key('nutrition-error'), findsOneWidget);
          expect(find.text('Profile saved.'), findsNothing);
          expect(repository.patches.single, {
            'daily_calories_target': 3204,
            'daily_protein_target_g': 160,
            'daily_carbs_target_g': 400,
            'daily_fat_target_g': 107,
          });
          expect(repository.calculations, 1);

          repository.saveHandler = null;
          await tap(tester, 'nutrition-save');
          expect(repository.patches, hasLength(2));
          expect(repository.patches.last, repository.patches.first);
          expect(repository.calculations, 1);
          expect(key('home-screen'), findsOneWidget);
          expect(find.text('Profile saved.'), findsOneWidget);
        },
      );
    }
  }

  testWidgets(
    'W7 no targets explicitly saves displayed estimate; locale retains estimate',
    (tester) async {
      configure();
      repository.json.addAll(nutritionJson(full: true));
      for (final key in [
        'daily_calories_target',
        'daily_protein_target_g',
        'daily_carbs_target_g',
        'daily_fat_target_g',
      ]) {
        repository.json[key] = null;
      }
      await start(tester);
      await summary(tester);
      expect(repository.patches, isEmpty);
      expect(
        tester.widget<FilledButton>(key('nutrition-save')).onPressed,
        isNull,
      );
      await tap(tester, 'nutrition-calculate');
      expect(repository.patches, isEmpty);
      expect(find.text('Calories (kcal/day): 3204'), findsOneWidget);
      await container
          .read(localeControllerProvider.notifier)
          .setLocale(const Locale('ru'));
      await tester.pumpAndSettle();
      expect(find.text('Калории (ккал/день): 3204'), findsOneWidget);
      expect(repository.calculations, 1);
      await tap(tester, 'nutrition-save');
      expect(repository.patches.single, {
        'daily_calories_target': 3204,
        'daily_protein_target_g': 160,
        'daily_carbs_target_g': 400,
        'daily_fat_target_g': 107,
      });
      expect(key('home-screen'), findsOneWidget);
    },
  );
  testWidgets(
    'W7 partial targets preserve by default; unsupported reason never claims success',
    (tester) async {
      configure();
      repository.json.addAll(nutritionJson(full: true));
      repository.calculateHandler = (_) async =>
          NutritionUnsupported('2026-10-04', [NutritionUnsupportedReason.age]);
      await start(tester);
      await summary(tester);
      await tap(tester, 'nutrition-calculate');
      expect(find.text('The calculation supports ages 19–78.'), findsOneWidget);
      expect(find.text('Carbs (g/day): Not set'), findsOneWidget);
      await tap(tester, 'nutrition-save');
      expect(repository.patches, isEmpty);
      expect(key('home-screen'), findsOneWidget);
      expect(find.text('Profile saved.'), findsNothing);
    },
  );
  testWidgets(
    'W7 money validation retains comma draft/error across locale; pair clear and reopen',
    (tester) async {
      configure();
      repository.json.addAll(nutritionJson(full: true));
      await start(tester);
      await open(tester);
      for (var i = 0; i < 4; i++) {
        await tap(tester, 'nutrition-save');
      }
      final amount = find.descendant(
        of: key('preference-budgetAmount'),
        matching: find.byType(TextField),
      );
      await tester.ensureVisible(amount);
      await tester.enterText(amount, '50,125');
      await tap(tester, 'nutrition-save');
      expect(repository.patches, isEmpty);
      await container
          .read(localeControllerProvider.notifier)
          .setLocale(const Locale('ru'));
      await tester.pumpAndSettle();
      expect(tester.widget<TextField>(amount).controller!.text, '50,125');
      expect(
        tester.widget<TextField>(amount).decoration!.errorText,
        contains('Без округления'),
      );
      await tester.ensureVisible(amount);
      await tester.enterText(amount, '50,12');
      await tap(tester, 'nutrition-save');
      expect(repository.patches.single, {
        'weekly_food_budget_amount': '50.12',
        'budget_currency': 'EUR',
      });
      await tap(tester, 'nutrition-back');
      await tap(tester, 'nutrition-clear-budget');
      await tap(tester, 'nutrition-save');
      expect(repository.patches.last, {
        'weekly_food_budget_amount': null,
        'budget_currency': null,
      });
      await tap(tester, 'nutrition-exit');
      await summary(tester);
      expect(repository.patches, hasLength(2));
    },
  );
  for (final sameUser in [false, true]) {
    for (final action in ['calculate', 'confirm']) {
      for (final fail in [false, true]) {
        testWidgets(
          'W7 late $action $fail after ${sameUser ? 'A→A' : 'A→B'} no result/toast/navigation',
          (tester) async {
            configure();
            repository.json.addAll(nutritionJson(full: true));
            final calc = Completer<NutritionCalculation>();
            final save = Completer<NutritionProfile>();
            await start(tester);
            await summary(tester);
            final snapshot = NutritionCalculation.fromJson(
              calculationJson(profile: repository.json),
              date: '2026-10-04',
            );
            if (action == 'calculate') {
              repository.calculateHandler = (_) => calc.future;
              tester
                  .widget<OutlinedButton>(key('nutrition-calculate'))
                  .onPressed!();
            } else {
              await tap(tester, 'nutrition-calculate');
              await tester.ensureVisible(key('nutrition-select-estimate'));
              tester
                  .widget<CheckboxListTile>(key('nutrition-select-estimate'))
                  .onChanged!(true);
              await tester.pump();
              repository.saveHandler = (_) => save.future;
              tester.widget<FilledButton>(key('nutrition-save')).onPressed!();
            }
            await tester.pump();
            final controller = container.read(authControllerProvider.notifier);
            await controller.logout();
            await tester.pumpAndSettle();
            if (!sameUser) {
              loginUser = AuthUser(
                id: 'synthetic-b',
                email: 'b@example.com',
                fullName: null,
                createdAt: DateTime.utc(2026),
                updatedAt: DateTime.utc(2026),
              );
            }
            repository.calculateHandler = null;
            repository.saveHandler = null;
            await controller.login(
              email: 'synthetic@example.com',
              password: 'synthetic-password',
            );
            await tester.pumpAndSettle();
            await open(tester);
            select(tester, NutritionField.goal, 'gain_weight');
            await tester.pump();
            if (action == 'calculate') {
              if (fail) {
                calc.completeError(StateError('synthetic'));
              } else {
                calc.complete(snapshot);
              }
            } else {
              if (fail) {
                save.completeError(StateError('synthetic'));
              } else {
                save.complete(
                  NutritionProfile.fromJson(nutritionJson(full: true)),
                );
              }
            }
            await tester.pumpAndSettle();
            expect(find.text('Step 1 of 6'), findsOneWidget);
            expect(key('nutrition-error'), findsNothing);
            expect(find.text('Profile saved.'), findsNothing);
            expect(find.text('Calories (kcal/day): 3204'), findsNothing);
            expect(
              tester
                  .widget<DropdownButtonFormField<String>>(
                    key('nutrition-goal'),
                  )
                  .initialValue,
              'gain_weight',
            );
          },
        );
      }
    }
  }
  testWidgets(
    'W7 list controls preserve dirty input on Back/locale, save only likes and reopen',
    (tester) async {
      configure();
      repository.json.addAll(nutritionJson(full: true));
      repository.json['liked_ingredients'] = ['rice', 'rice'];
      repository.json['diet_type'] = 'custom diet';
      await start(tester);
      await open(tester);
      for (var i = 0; i < 3; i++) {
        await tap(tester, 'nutrition-save');
      }
      Finder likes() => find.descendant(
        of: key('ingredients-likes'),
        matching: find.byType(TextField),
      );
      await tester.ensureVisible(likes().first);
      await tester.enterText(likes().first, 'peanuts');
      await tap(tester, 'nutrition-back');
      await tap(tester, 'nutrition-save');
      expect(
        tester.widget<TextField>(likes().first).controller!.text,
        'peanuts',
      );
      await container
          .read(localeControllerProvider.notifier)
          .setLocale(const Locale('uk'));
      await tester.pumpAndSettle();
      expect(
        tester.widget<TextField>(likes().first).controller!.text,
        'peanuts',
      );
      await tap(tester, 'nutrition-exit');
      await tap(tester, 'nutrition-stay');
      await tap(tester, 'nutrition-save');
      expect(repository.patches.single, {
        'liked_ingredients': ['peanuts', 'rice'],
      });
      expect(repository.json['diet_type'], 'custom diet');
      expect(repository.json['allergies'], ['synthetic-allergen']);
      await tap(tester, 'nutrition-exit');
      await open(tester);
      for (var i = 0; i < 3; i++) {
        await tap(tester, 'nutrition-save');
      }
      expect(
        tester.widget<TextField>(likes().first).controller!.text,
        'peanuts',
      );
      final remove = find
          .descendant(
            of: key('ingredients-likes'),
            matching: find.byType(IconButton),
          )
          .first;
      await tester.ensureVisible(remove);
      await tester.tap(remove);
      await tester.pumpAndSettle();
      expect(tester.widget<TextField>(likes()).controller!.text, 'rice');
      await tap(tester, 'nutrition-save');
      expect(repository.patches.last, {
        'liked_ingredients': ['rice'],
      });
    },
  );
}
