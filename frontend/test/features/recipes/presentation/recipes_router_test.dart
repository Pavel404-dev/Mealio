import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mealio/app/app.dart';
import 'package:mealio/app/router/app_router.dart';
import 'package:mealio/core/auth/auth_token_pair.dart';
import 'package:mealio/core/localization/locale_controller.dart';
import 'package:mealio/core/network/api_client.dart';
import 'package:mealio/core/network/session_request.dart';
import 'package:mealio/core/storage/secure_storage_provider.dart';
import 'package:mealio/features/auth/data/auth_repository.dart';
import 'package:mealio/features/auth/presentation/auth_controller.dart';
import 'package:mealio/l10n/generated/app_localizations.dart';

import '../../../helpers/auth_test_fakes.dart';
import '../../../helpers/locale_test_fakes.dart';
import '../../../helpers/recipe_test_fakes.dart';

void main() {
  late FakeHttpClientAdapter adapter;
  late FakeSecureStorageService storage;
  late FakeAuthRepository auth;
  late ProviderContainer container;

  Finder key(String name) => find.byKey(Key(name));

  setUp(() {
    adapter = FakeHttpClientAdapter();
    auth = FakeAuthRepository(
      restoreHandler: () async => testAuthUser,
      logoutHandler: () => storage.deleteTokenPair(),
      loginHandler: ({required email, required password}) async {
        await storage.writeTokenPair(
          const AuthTokenPair(
            accessToken: 'test-access-B',
            refreshToken: 'test-refresh-B',
          ),
        );
        return testAuthUser; // Same user, new login lifetime.
      },
    );
  });

  Future<void> pumpApp(WidgetTester tester) async {
    // Construct queued async storage inside the widget test's FakeAsync zone.
    storage = FakeSecureStorageService(
      accessToken: 'test-access-A',
      refreshToken: 'test-refresh-A',
    );
    container = ProviderContainer(
      overrides: [
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

  Future<void> openRecipes(WidgetTester tester, {bool settle = true}) async {
    await tester.scrollUntilVisible(key('recipes-card'), 200);
    await tester.tap(key('recipes-card'));
    if (settle) {
      await tester.pumpAndSettle();
    } else {
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
    }
  }

  testWidgets(
    'Home opens the real recipe repository/provider/screen and Back returns Home',
    (tester) async {
      adapter.enqueue(FakeHttpResponse(statusCode: 200, body: [recipeJson()]));
      await pumpApp(tester);
      await openRecipes(tester);
      expect(key('recipes-screen'), findsOneWidget);
      expect(find.text('Calories (kcal): 330'), findsOneWidget);
      expect(adapter.requests, hasLength(1));
      expect(adapter.requests.single.path, '/recipes');
      expect(adapter.requests.single.queryParameters, {
        'limit': 50,
        'offset': 0,
      });
      await tester.pageBack();
      await tester.pumpAndSettle();
      expect(key('home-screen'), findsOneWidget);
      expect(key('recipes-screen'), findsNothing);
    },
  );

  testWidgets(
    'authenticated direct route loads recipes without navigation extras',
    (tester) async {
      adapter.enqueue(const FakeHttpResponse(statusCode: 200, body: []));
      await pumpApp(tester);
      GoRouter.of(tester.element(key('home-screen'))).go('/recipes');
      await tester.pumpAndSettle();
      expect(key('recipes-empty-state'), findsOneWidget);
      expect(adapter.requests, hasLength(1));
    },
  );

  testWidgets(
    'unauthenticated direct route returns to Login without recipe requests',
    (tester) async {
      auth.restoreHandler = () async => null;
      await pumpApp(tester);
      GoRouter.of(tester.element(key('login-screen'))).go('/recipes');
      await tester.pumpAndSettle();
      expect(key('login-screen'), findsOneWidget);
      expect(key('recipes-screen'), findsNothing);
      expect(adapter.requests, isEmpty);
    },
  );

  testWidgets(
    'locale change, same-session auth reload and refresh keep loaded pages',
    (tester) async {
      adapter.enqueue(FakeHttpResponse(statusCode: 200, body: [recipeJson()]));
      await pumpApp(tester);
      await openRecipes(tester);
      await container
          .read(localeControllerProvider.notifier)
          .setLocale(const Locale('ru'));
      await tester.pumpAndSettle();
      expect(find.text('4 порции'), findsOneWidget);
      expect(find.text('Жиры (г): 7,2'), findsOneWidget);
      final rotated = await storage.replaceTokenPairIfRefreshTokenMatches(
        expectedRefreshToken: 'test-refresh-A',
        pair: const AuthTokenPair(
          accessToken: 'test-rotated',
          refreshToken: 'test-rotated-refresh',
        ),
      );
      expect(rotated, isTrue);
      await container.read(authControllerProvider.notifier).reloadCurrentUser();
      await tester.pumpAndSettle();
      expect(find.text('Saved recipe'), findsOneWidget);
      expect(adapter.requests, hasLength(1));
      expect(storage.sessionLifetime, 0);
    },
  );

  testWidgets(
    'visible error retranslates without refetch; Retry uses current locale',
    (tester) async {
      adapter.enqueue(
        const FakeHttpResponse(
          statusCode: 500,
          body: {'detail': 'synthetic-private-detail'},
        ),
      );
      await pumpApp(tester);
      await openRecipes(tester);
      await container
          .read(localeControllerProvider.notifier)
          .setLocale(const Locale('uk'));
      await tester.pumpAndSettle();
      final uk = await AppLocalizations.delegate.load(const Locale('uk'));
      expect(find.text(uk.recipesLoadError), findsOneWidget);
      expect(find.text(uk.retry), findsOneWidget);
      expect(find.textContaining('synthetic-private-detail'), findsNothing);
      expect(adapter.requests, hasLength(1));
      adapter.enqueue(const FakeHttpResponse(statusCode: 200, body: []));
      await tester.tap(key('recipes-retry'));
      await tester.pumpAndSettle();
      expect(find.text(uk.recipesEmpty), findsOneWidget);
      expect(adapter.requests, hasLength(2));
    },
  );

  for (final initial in [true, false]) {
    for (final lateError in [false, true]) {
      testWidgets(
        'same-user relogin isolates late ${initial ? 'initial' : 'next'} page ${lateError ? 'error' : 'success'}',
        (tester) async {
          var newLogin = false;
          final pending = Completer<FakeHttpResponse>();
          adapter.responseHandler = (request) {
            if (newLogin) {
              return FakeHttpResponse(
                statusCode: 200,
                body: [recipeJson(title: 'New session recipe')],
              );
            }
            if (!initial && request.queryParameters['offset'] == 0) {
              return FakeHttpResponse(
                statusCode: 200,
                body: [
                  for (var i = 0; i < 50; i++)
                    recipeJson(id: 'old-$i', title: 'Old session recipe $i'),
                ],
              );
            }
            return pending.future;
          };
          await pumpApp(tester);
          await openRecipes(tester, settle: !initial);
          if (!initial) {
            await tester.scrollUntilVisible(
              key('recipes-load-more'),
              500,
              maxScrolls: 70,
            );
            await tester.tap(key('recipes-load-more'));
            await tester.pump();
            await tester.pump(const Duration(milliseconds: 1));
          }
          expect(adapter.requests.length, initial ? 1 : 2);
          expect(adapter.requests.last.extra[sessionLifetimeKey], 0);
          await container.read(authControllerProvider.notifier).logout();
          await tester.pumpAndSettle();
          expect(key('login-screen'), findsOneWidget);
          newLogin = true;
          await container
              .read(authControllerProvider.notifier)
              .login(email: 'test@example.com', password: 'test-password');
          await tester.pumpAndSettle();
          await openRecipes(tester);
          expect(find.text('New session recipe'), findsOneWidget);
          expect(adapter.requests.last.extra[sessionLifetimeKey], 2);
          pending.complete(
            FakeHttpResponse(
              statusCode: lateError ? 401 : 200,
              body: lateError ? {} : [recipeJson(title: 'Late old recipe')],
            ),
          );
          await tester.pumpAndSettle();
          expect(find.text('New session recipe'), findsOneWidget);
          expect(find.textContaining('Old session recipe'), findsNothing);
          expect(find.text('Late old recipe'), findsNothing);
          expect(key('recipes-error-message'), findsNothing);
          expect(storage.accessToken, 'test-access-B');
          expect(adapter.requests.length, initial ? 2 : 3);
        },
      );
    }
  }

  Future<void> openDetail(
    WidgetTester tester,
    String id, {
    bool settle = true,
  }) async {
    container.read(appRouterProvider).go('/recipes/${Uri.encodeComponent(id)}');
    if (settle) {
      await tester.pumpAndSettle();
    } else {
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
    }
  }

  testWidgets(
    'list card fetches fresh detail/names; Back preserves loaded list',
    (tester) async {
      adapter.responseHandler = (request) => FakeHttpResponse(
        statusCode: 200,
        body: switch (request.path) {
          '/recipes' => [recipeJson(title: 'List title')],
          '/recipes/recipe-1' => recipeJson(title: 'Latest server title'),
          '/ingredients/ingredient-1' => recipeIngredientJson(
            name: 'Server ingredient',
          ),
          _ => throw StateError('Unexpected test request'),
        },
      );
      await pumpApp(tester);
      await openRecipes(tester);
      await tester.tap(find.text('List title'));
      await tester.pumpAndSettle();
      expect(find.text('Latest server title'), findsOneWidget);
      expect(find.text('Calories (kcal): 330'), findsOneWidget);
      expect(find.text('4 servings'), findsOneWidget);
      await tester.scrollUntilVisible(find.text('Server ingredient'), 200);
      await tester.pumpAndSettle();
      expect(find.text('200 g'), findsOneWidget);
      await tester.tap(key('recipe-detail-back'));
      await tester.pumpAndSettle();
      expect(key('recipes-list'), findsOneWidget);
      expect(find.text('List title'), findsOneWidget);
      expect(adapter.requests.map((e) => e.path), [
        '/recipes',
        '/recipes/recipe-1',
        '/ingredients/ingredient-1',
      ]);
    },
  );

  testWidgets(
    'direct detail entry needs no extra and Back falls back to the list',
    (tester) async {
      adapter.responseHandler = (request) => FakeHttpResponse(
        statusCode: 200,
        body: request.path == '/recipes'
            ? []
            : (recipeJson()..['recipe_ingredients'] = []),
      );
      await pumpApp(tester);
      await openDetail(tester, 'recipe-1');
      expect(key('recipe-detail-content'), findsOneWidget);
      await tester.tap(key('recipe-detail-back'));
      await tester.pumpAndSettle();
      expect(key('recipes-empty-state'), findsOneWidget);
      expect(adapter.requests.map((e) => e.path), [
        '/recipes/recipe-1',
        '/recipes',
      ]);
    },
  );

  testWidgets(
    'unauthenticated detail route cannot send recipe or catalog requests',
    (tester) async {
      auth.restoreHandler = () async => null;
      await pumpApp(tester);
      await openDetail(tester, 'recipe-1');
      expect(key('login-screen'), findsOneWidget);
      expect(adapter.requests, isEmpty);
    },
  );

  testWidgets(
    'detail 404 has safe unavailable copy and explicit retry can recover',
    (tester) async {
      adapter.enqueue(
        const FakeHttpResponse(
          statusCode: 404,
          body: {'detail': 'synthetic-private-detail'},
        ),
      );
      await pumpApp(tester);
      await openDetail(tester, 'recipe-1');
      expect(find.text('This recipe is no longer available.'), findsOneWidget);
      expect(adapter.requests, hasLength(1));
      await container
          .read(localeControllerProvider.notifier)
          .setLocale(const Locale('ru'));
      await tester.pumpAndSettle();
      expect(find.text('Этот рецепт больше недоступен.'), findsOneWidget);
      expect(adapter.requests, hasLength(1));
      adapter.enqueue(
        FakeHttpResponse(
          statusCode: 200,
          body: recipeJson()..['recipe_ingredients'] = [],
        ),
      );
      await tester.tap(key('recipe-detail-retry'));
      await tester.pumpAndSettle();
      expect(find.text('Saved recipe'), findsOneWidget);
      expect(adapter.requests, hasLength(2));
    },
  );

  testWidgets(
    'detail locale/auth reload keeps names, instructions and pending identity',
    (tester) async {
      final json = recipeJson();
      (json['recipe_ingredients'] as List).single['quantity_g'] = '12.25';
      adapter.responseHandler = (request) => FakeHttpResponse(
        statusCode: 200,
        body: request.path.startsWith('/recipes/')
            ? json
            : recipeIngredientJson(name: 'Server name {raw}'),
      );
      await pumpApp(tester);
      await openDetail(tester, 'recipe-1');
      await container
          .read(localeControllerProvider.notifier)
          .setLocale(const Locale('uk'));
      await container.read(authControllerProvider.notifier).reloadCurrentUser();
      await tester.pumpAndSettle();
      expect(find.text('4 порції'), findsOneWidget);
      await tester.scrollUntilVisible(find.text('Server name {raw}'), 200);
      await tester.pumpAndSettle();
      final uk = await AppLocalizations.delegate.load(const Locale('uk'));
      expect(find.text(uk.quantityGrams('12,25')), findsOneWidget);
      await tester.scrollUntilVisible(key('recipe-detail-instructions'), 200);
      await tester.pumpAndSettle();
      expect(find.text('First step.\nSecond step.'), findsOneWidget);
      expect(adapter.requests, hasLength(2));
    },
  );

  for (final namesPending in [false, true]) {
    for (final lateError in [false, true]) {
      testWidgets(
        'changing ID cancels old ${namesPending ? 'catalog' : 'recipe'} and ignores late ${lateError ? 'error' : 'data'}',
        (tester) async {
          var newer = false;
          final pending = Completer<FakeHttpResponse>();
          adapter.responseHandler = (request) {
            if (request.path == '/recipes/new') {
              return FakeHttpResponse(
                statusCode: 200,
                body: recipeJson(id: 'new', title: 'New ID detail'),
              );
            }
            if (request.path == '/recipes/old') {
              return namesPending
                  ? FakeHttpResponse(
                      statusCode: 200,
                      body: recipeJson(id: 'old', title: 'Old ID detail'),
                    )
                  : pending.future;
            }
            if (newer) {
              return FakeHttpResponse(
                statusCode: 200,
                body: recipeIngredientJson(name: 'New ID name'),
              );
            }
            return pending.future;
          };
          await pumpApp(tester);
          await openDetail(tester, 'old', settle: false);
          final oldRequest = adapter.requests.last;
          expect(adapter.requests, hasLength(namesPending ? 2 : 1));
          newer = true;
          await openDetail(tester, 'new');
          expect(find.text('New ID detail'), findsOneWidget);
          expect(oldRequest.cancelToken?.isCancelled, isTrue);
          pending.complete(
            FakeHttpResponse(
              statusCode: lateError ? 500 : 200,
              body: lateError
                  ? {}
                  : namesPending
                  ? recipeIngredientJson(name: 'Old ID name')
                  : recipeJson(id: 'old', title: 'Old ID detail'),
            ),
          );
          await tester.pumpAndSettle();
          expect(find.text('New ID detail'), findsOneWidget);
          expect(find.text('Old ID detail'), findsNothing);
          expect(key('recipe-detail-error'), findsNothing);
          expect(adapter.requests, hasLength(namesPending ? 4 : 3));
        },
      );

      testWidgets(
        'same-user relogin cancels pending ${namesPending ? 'catalog' : 'recipe'} ${lateError ? 'error' : 'data'}',
        (tester) async {
          var newLogin = false;
          final pending = Completer<FakeHttpResponse>();
          adapter.responseHandler = (request) {
            final recipe = request.path.startsWith('/recipes/');
            if (newLogin) {
              return FakeHttpResponse(
                statusCode: 200,
                body: recipe
                    ? recipeJson(title: 'New login detail')
                    : recipeIngredientJson(name: 'New login name'),
              );
            }
            if (recipe && namesPending) {
              return FakeHttpResponse(
                statusCode: 200,
                body: recipeJson(title: 'Old login detail'),
              );
            }
            return pending.future;
          };
          await pumpApp(tester);
          await openDetail(tester, 'recipe-1', settle: false);
          final oldRequest = adapter.requests.last;
          expect(adapter.requests, hasLength(namesPending ? 2 : 1));
          await container.read(authControllerProvider.notifier).logout();
          await tester.pumpAndSettle();
          expect(key('login-screen'), findsOneWidget);
          expect(oldRequest.cancelToken?.isCancelled, isTrue);
          newLogin = true;
          await container
              .read(authControllerProvider.notifier)
              .login(email: 'test@example.com', password: 'test-password');
          await tester.pumpAndSettle();
          await openDetail(tester, 'recipe-1');
          expect(find.text('New login detail'), findsOneWidget);
          expect(adapter.requests.last.extra[sessionLifetimeKey], 2);
          pending.complete(
            FakeHttpResponse(
              statusCode: lateError ? 401 : 200,
              body: lateError
                  ? {}
                  : namesPending
                  ? recipeIngredientJson(name: 'Old login name')
                  : recipeJson(title: 'Old login detail'),
            ),
          );
          await tester.pumpAndSettle();
          expect(find.text('New login detail'), findsOneWidget);
          expect(find.text('Old login detail'), findsNothing);
          expect(key('recipe-detail-error'), findsNothing);
          expect(storage.accessToken, 'test-access-B');
          expect(adapter.requests, hasLength(namesPending ? 4 : 3));
        },
      );
    }
  }
}
