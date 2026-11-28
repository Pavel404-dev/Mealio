import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mealio/app/app.dart';
import 'package:mealio/core/config/app_config.dart';
import 'package:mealio/core/localization/locale_controller.dart';
import 'package:mealio/core/network/api_client.dart';
import 'package:mealio/core/storage/secure_storage_provider.dart';
import 'package:mealio/features/auth/data/auth_repository.dart';
import 'package:mealio/features/auth/presentation/auth_controller.dart';

import '../../../helpers/auth_test_fakes.dart';
import '../../../helpers/locale_test_fakes.dart';
import '../../../helpers/recipe_test_fakes.dart';

const _recipeId = 'c7c69d0e-d6c4-48c6-8b0e-3e068af3e96a';
const _secondRecipeId = 'c775f031-f980-4843-a8fb-a17e4fd86e05';

class _TestConfig extends AppConfig {
  const _TestConfig();

  @override
  String get apiBaseUrl => 'http://test.local/api/v1';
}

FakeHttpResponse previewFor(
  RequestOptions options, {
  String recipeId = _recipeId,
  String calories = '103.13',
}) {
  final payload = options.data as Map<String, Object>;
  return FakeHttpResponse(
    statusCode: 200,
    body: {
      'items': [
        for (final slot in payload['meal_types']! as List<String>)
          {
            'recipe_id': recipeId,
            'planned_date': payload['planned_date'],
            'meal_type': slot,
            'planned_servings': '1.25',
          },
      ],
      'nutrition': {
        'total_calories': calories,
        'total_protein_g': '19.38',
        'total_carbs_g': '0.00',
        'total_fat_g': '2.25',
      },
      'target_fit': {'status': 'not_evaluated', 'tolerance_percent': 10},
    },
  );
}

void main() {
  late FakeHttpClientAdapter adapter;
  late ProviderContainer container;

  Finder key(String name) => find.byKey(Key(name));
  final generate = key('meal-plan-preview-generate');

  setUp(() => adapter = FakeHttpClientAdapter());

  Future<void> pumpApp(WidgetTester tester, {bool authenticated = true}) async {
    final storage = FakeSecureStorageService(
      accessToken: 'test-access',
      refreshToken: 'test-refresh',
    );
    final auth = FakeAuthRepository(
      restoreHandler: () async => authenticated ? testAuthUser : null,
      logoutHandler: () => storage.deleteTokenPair(),
    );
    container = ProviderContainer(
      overrides: [
        appConfigProvider.overrideWithValue(const _TestConfig()),
        apiClientProvider.overrideWithValue(
          ApiClient(createFakeDio(adapter), storage: storage),
        ),
        authRepositoryProvider.overrideWithValue(auth),
        secureStorageServiceProvider.overrideWithValue(storage),
        localeStorageProvider.overrideWithValue(MemoryLocaleStorage()),
      ],
    );
    addTearDown(container.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(container: container, child: const MealioApp()),
    );
    await tester.pumpAndSettle();
  }

  Future<void> openPreview(WidgetTester tester) async {
    await tester.scrollUntilVisible(key('meal-plan-card'), 200);
    await tester.tap(key('meal-plan-card'));
    await tester.pumpAndSettle();
    expect(key('meal-plan-preview-screen'), findsOneWidget);
  }

  Future<void> chooseDate(WidgetTester tester, DateTime date) async {
    final dateButton = key('meal-plan-preview-date');
    await tester.ensureVisible(dateButton);
    await tester.tap(dateButton);
    await tester.pumpAndSettle();
    final dialog = find.byType(DatePickerDialog);
    final labels = MaterialLocalizations.of(tester.element(dialog));
    await tester.tap(find.byTooltip(labels.inputDateModeButtonLabel));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.descendant(of: dialog, matching: find.byType(TextField)),
      labels.formatCompactDate(date),
    );
    await tester.tap(find.text(labels.okButtonLabel));
    await tester.pumpAndSettle();
    expect(find.text(labels.formatFullDate(date)), findsOneWidget);
  }

  Future<void> submitPreview(WidgetTester tester) async {
    await tester.ensureVisible(generate);
    await tester.tap(generate);
    await tester.pumpAndSettle();
  }

  testWidgets(
    'opens from Home, blocks double taps, retries and renders a day',
    (tester) async {
      final pending = Completer<FakeHttpResponse>();
      var submits = 0;
      adapter.responseHandler = (request) {
        if (request.method == 'GET') {
          expect(request.path, '/recipes/$_recipeId');
          return FakeHttpResponse(
            statusCode: 200,
            body: recipeJson(id: _recipeId, title: 'Test recipe'),
          );
        }
        submits += 1;
        return submits == 1 ? pending.future : previewFor(request);
      };
      await pumpApp(tester);
      await openPreview(tester);
      expect(adapter.requests, isEmpty);
      await tester.tap(key('meal-plan-slot-breakfast'));
      await tester.pump();
      await tester.tap(key('meal-plan-slot-dinner'));
      await tester.pump();
      await tester.tap(generate);
      await tester.tap(generate);
      await tester.tap(key('meal-plan-slot-snack'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 1));
      expect(find.text('Generating preview…'), findsOneWidget);
      expect(
        tester.widget<FilterChip>(key('meal-plan-slot-snack')).selected,
        isFalse,
      );
      expect(adapter.requests, hasLength(1));
      expect(adapter.requests.first.data['meal_types'], ['lunch']);
      final firstKey = adapter.requests.first.headers['Idempotency-Key'];
      expect(
        firstKey,
        isA<String>().having((value) => value.length, 'length', 32),
      );

      pending.complete(
        const FakeHttpResponse.error(DioExceptionType.connectionError),
      );
      await tester.pumpAndSettle();
      expect(key('meal-plan-preview-error'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);
      await tester.tap(generate);
      await tester.pumpAndSettle();
      expect(adapter.requests[1].headers['Idempotency-Key'], firstKey);
      expect(adapter.requests[1].data, adapter.requests[0].data);
      expect(key('meal-plan-preview-result'), findsOneWidget);
      await tester.scrollUntilVisible(find.text('Test recipe'), 150);
      expect(find.text('Planned servings 1.25'), findsOneWidget);
      expect(find.text('Calories (kcal): 103.13'), findsOneWidget);
      await tester.ensureVisible(generate);
      await tester.tap(generate);
      await tester.pumpAndSettle();
      expect(adapter.requests[3].headers['Idempotency-Key'], isNot(firstKey));
      expect(
        adapter.requests
            .where((request) => request.method == 'POST')
            .every(
              (request) =>
                  request.uri.path == '/api/v2/meal-plans/ai/generate-preview',
            ),
        isTrue,
      );
    },
  );

  testWidgets('changing meals after a coverage error starts a new request', (
    tester,
  ) async {
    adapter.responseHandler = (_) => const FakeHttpResponse(
      statusCode: 422,
      body: {'detail': 'Untrusted server detail'},
    );
    await pumpApp(tester);
    await openPreview(tester);
    await tester.tap(generate);
    await tester.pumpAndSettle();
    expect(find.textContaining('suitable saved recipes'), findsOneWidget);
    expect(find.textContaining('Untrusted server detail'), findsNothing);
    await tester.tap(key('meal-plan-slot-snack'));
    await tester.pumpAndSettle();
    expect(key('meal-plan-preview-error'), findsNothing);
    await tester.tap(generate);
    await tester.pumpAndSettle();
    expect(adapter.requests.last.data['meal_types'], [
      'breakfast',
      'lunch',
      'dinner',
      'snack',
    ]);
    expect(
      adapter.requests.last.headers['Idempotency-Key'],
      isNot(adapter.requests.first.headers['Idempotency-Key']),
    );
  });

  testWidgets('restores each date with its own meals, recipe and totals', (
    tester,
  ) async {
    final first = DateUtils.addDaysToDate(DateTime.now(), 2);
    final second = DateUtils.addDaysToDate(first, 1);
    final dates = [
      first.toIso8601String().split('T').first,
      second.toIso8601String().split('T').first,
    ];
    final lunch = key('meal-plan-slot-lunch');
    final dinner = key('meal-plan-slot-dinner');
    adapter.responseHandler = (request) {
      if (request.method == 'GET') {
        final id = request.uri.pathSegments.last;
        return FakeHttpResponse(
          statusCode: 200,
          body: recipeJson(
            id: id,
            title: id == _recipeId ? 'First day recipe' : 'Second day recipe',
          ),
        );
      }
      return request.data['planned_date'] == dates.last
          ? previewFor(request, recipeId: _secondRecipeId, calories: '206.25')
          : previewFor(request);
    };
    await pumpApp(tester);
    await openPreview(tester);

    await chooseDate(tester, first);
    await tester.tap(key('meal-plan-slot-breakfast'));
    await tester.pump();
    await tester.tap(dinner);
    await tester.pump();
    await submitPreview(tester);

    await chooseDate(tester, second);
    expect(key('meal-plan-preview-result'), findsNothing);
    expect(tester.widget<FilterChip>(lunch).selected, isTrue);
    await tester.tap(lunch);
    await tester.pump();
    await tester.tap(dinner);
    await tester.pump();
    await submitPreview(tester);

    final posts = adapter.requests.where((request) => request.method == 'POST');
    expect(posts.map((request) => request.data['planned_date']), dates);
    expect(posts.map((request) => request.data['meal_types']), [
      ['lunch'],
      ['dinner'],
    ]);
    final requestCount = adapter.requests.length;

    await chooseDate(tester, first);
    expect(tester.widget<FilterChip>(lunch).selected, isTrue);
    expect(tester.widget<FilterChip>(dinner).selected, isFalse);
    expect(find.text('Calories (kcal): 103.13'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('First day recipe'), 100);
    expect(find.text('Second day recipe'), findsNothing);

    await chooseDate(tester, second);
    expect(tester.widget<FilterChip>(lunch).selected, isFalse);
    expect(tester.widget<FilterChip>(dinner).selected, isTrue);
    expect(find.text('Calories (kcal): 206.25'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Second day recipe'), 100);
    expect(find.text('First day recipe'), findsNothing);

    await tester.ensureVisible(dinner);
    await tester.tap(dinner);
    await tester.pumpAndSettle();
    expect(key('meal-plan-preview-result'), findsNothing);
    await chooseDate(tester, first);
    expect(find.text('Calories (kcal): 103.13'), findsOneWidget);
    expect(adapter.requests, hasLength(requestCount));
  });

  testWidgets('returning to a failed date retries the original request', (
    tester,
  ) async {
    final first = DateTime(2026, 11, 26);
    adapter.responseHandler = (request) {
      if (request.method == 'GET') {
        return FakeHttpResponse(
          statusCode: 200,
          body: recipeJson(id: _recipeId, title: 'Test recipe'),
        );
      }
      return adapter.requests.length == 1
          ? const FakeHttpResponse.error(DioExceptionType.connectionError)
          : previewFor(request);
    };
    await pumpApp(tester);
    await openPreview(tester);
    await chooseDate(tester, first);
    await submitPreview(tester);
    expect(find.text('Retry'), findsOneWidget);
    final original = adapter.requests.single;

    await chooseDate(tester, DateTime(2026, 11, 27));
    expect(key('meal-plan-preview-error'), findsNothing);
    expect(find.text('Generate preview'), findsOneWidget);
    await chooseDate(tester, first);
    expect(find.text('Retry'), findsOneWidget);
    expect(adapter.requests, hasLength(1));

    await submitPreview(tester);
    final retry = adapter.requests[1];
    expect(retry.data, original.data);
    expect(
      retry.headers['Idempotency-Key'],
      original.headers['Idempotency-Key'],
    );
    expect(key('meal-plan-preview-result'), findsOneWidget);
  });

  testWidgets('an idempotency conflict starts a fresh preview on retry', (
    tester,
  ) async {
    adapter.responseHandler = (_) =>
        const FakeHttpResponse(statusCode: 409, body: {});
    await pumpApp(tester);
    await openPreview(tester);
    await tester.tap(generate);
    await tester.pumpAndSettle();
    expect(key('meal-plan-preview-error'), findsOneWidget);
    await tester.tap(generate);
    await tester.pumpAndSettle();
    expect(adapter.requests, hasLength(2));
    expect(
      adapter.requests[1].headers['Idempotency-Key'],
      isNot(adapter.requests[0].headers['Idempotency-Key']),
    );
    expect(adapter.requests[1].data, adapter.requests[0].data);
  });

  testWidgets('unauthenticated deep link stays at Login', (tester) async {
    await pumpApp(tester, authenticated: false);
    GoRouter.of(tester.element(key('login-screen'))).go('/meal-plan');
    await tester.pumpAndSettle();
    expect(key('login-screen'), findsOneWidget);
    expect(key('meal-plan-preview-screen'), findsNothing);
    expect(adapter.requests, isEmpty);
  });

  testWidgets('clears a previously viewed day across login sessions', (
    tester,
  ) async {
    final first = DateTime(2026, 11, 26);
    adapter.responseHandler = (request) => request.method == 'GET'
        ? FakeHttpResponse(
            statusCode: 200,
            body: recipeJson(id: _recipeId, title: 'Test recipe'),
          )
        : previewFor(request);
    await pumpApp(tester);
    await openPreview(tester);
    await chooseDate(tester, first);
    await submitPreview(tester);
    expect(key('meal-plan-preview-result'), findsOneWidget);
    await chooseDate(tester, DateTime(2026, 11, 27));
    final requestCount = adapter.requests.length;

    final auth = container.read(authControllerProvider.notifier);
    await auth.logout();
    await tester.pumpAndSettle();
    expect(key('login-screen'), findsOneWidget);
    await auth.login(email: testAuthUser.email, password: 'test-only-password');
    await tester.pumpAndSettle();
    await openPreview(tester);
    await chooseDate(tester, first);
    expect(key('meal-plan-preview-result'), findsNothing);
    expect(find.text('Generate preview'), findsOneWidget);
    expect(adapter.requests, hasLength(requestCount));
  });

  testWidgets(
    'logout cancels a pending preview before reading recipe details',
    (tester) async {
      final pending = Completer<FakeHttpResponse>();
      adapter.responseHandler = (_) => pending.future;
      await pumpApp(tester);
      await openPreview(tester);
      await tester.tap(generate);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 1));
      expect(adapter.requests, hasLength(1));
      await container.read(authControllerProvider.notifier).logout();
      await tester.pumpAndSettle();
      pending.complete(previewFor(adapter.requests.single));
      await tester.pumpAndSettle();
      expect(key('login-screen'), findsOneWidget);
      expect(key('meal-plan-preview-result'), findsNothing);
      expect(adapter.requests, hasLength(1));
    },
  );
}
