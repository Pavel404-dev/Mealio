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

class _TestConfig extends AppConfig {
  const _TestConfig();

  @override
  String get apiBaseUrl => 'http://test.local/api/v1';
}

FakeHttpResponse previewFor(RequestOptions options) {
  final payload = options.data as Map<String, Object>;
  return FakeHttpResponse(
    statusCode: 200,
    body: {
      'items': [
        for (final slot in payload['meal_types']! as List<String>)
          {
            'recipe_id': _recipeId,
            'planned_date': payload['planned_date'],
            'meal_type': slot,
            'planned_servings': '1.25',
          },
      ],
      'nutrition': {
        'total_calories': '103.13',
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
