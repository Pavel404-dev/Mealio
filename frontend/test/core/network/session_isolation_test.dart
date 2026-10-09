import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/auth/auth_token_pair.dart';
import 'package:mealio/core/network/api_client.dart';
import 'package:mealio/core/network/auth_interceptor.dart';
import 'package:mealio/core/network/token_refresh_coordinator.dart';

import '../../helpers/auth_test_fakes.dart';

const pairA = AuthTokenPair(accessToken: 'access-A', refreshToken: 'refresh-A');
const pairB = AuthTokenPair(accessToken: 'access-B', refreshToken: 'refresh-B');
const rotatedA = FakeHttpResponse(
  statusCode: 200,
  body: {
    'access_token': 'rotated-A',
    'refresh_token': 'rotated-refresh-A',
    'token_type': 'bearer',
  },
);
const rotatedB = FakeHttpResponse(
  statusCode: 200,
  body: {
    'access_token': 'rotated-B',
    'refresh_token': 'rotated-refresh-B',
    'token_type': 'bearer',
  },
);
const rejected = FakeHttpResponse(statusCode: 401, body: {});
const ok = FakeHttpResponse(statusCode: 200, body: {});

Future<Object?> outcome(Future<Object?> future) =>
    future.then<Object?>((value) => value, onError: (Object error) => error);

Completer<void> barrier() {
  final gate = Completer<void>();
  addTearDown(() {
    if (!gate.isCompleted) gate.complete();
  });
  return gate;
}

class Harness {
  Harness() {
    coordinator = TokenRefreshCoordinator(
      refreshDio: refreshDio,
      storage: storage,
      onSessionInvalidated: () => invalidations++,
    );
    dio.interceptors.add(
      AuthInterceptor(
        dio: dio,
        storage: storage,
        refreshCoordinator: coordinator,
      ),
    );
    api = ApiClient(dio, storage: storage);
  }
  final storage = FakeSecureStorageService(
    accessToken: pairA.accessToken,
    refreshToken: pairA.refreshToken,
  );
  final app = FakeHttpClientAdapter();
  final refresh = FakeHttpClientAdapter();
  late final dio = createFakeDio(app);
  late final refreshDio = createFakeDio(refresh);
  late final TokenRefreshCoordinator coordinator;
  late final ApiClient api;
  int invalidations = 0;

  void expectB() {
    expect(storage.accessToken, pairB.accessToken);
    expect(storage.refreshToken, pairB.refreshToken);
    expect(invalidations, 0);
  }
}

void main() {
  test(
    'ApiClient captures lifetime before the first interceptor microtask',
    () async {
      final h = Harness();
      h.app.enqueue(ok);
      final old = outcome(
        h.api.patch<Object?>('/pantry/A', data: {'quantity': 7}),
      );
      // No await: account switch precedes Dio's first interceptor invocation.
      await h.storage.writeTokenPair(pairB);
      expect(await old, isA<DioException>());
      expect(h.app.requests, isEmpty);
      h.expectB();
    },
  );

  for (final refreshRead in [false, true]) {
    test(
      'switch during ${refreshRead ? 'refresh' : 'access'} read blocks send',
      () async {
        final h = Harness();
        final started = barrier();
        final read = Completer<String?>();
        addTearDown(() {
          if (!read.isCompleted) read.complete(null);
        });
        if (refreshRead) {
          h.storage.refreshReadStarted = started;
          h.storage.pendingRefreshRead = read;
        } else {
          h.storage.accessReadStarted = started;
          h.storage.pendingRead = read;
        }
        final old = outcome(
          refreshRead
              ? h.coordinator.refreshTokens()
              : h.api.get<Object?>('/auth/me'),
        );
        await started.future;
        final loginB = h.storage.writeTokenPair(pairB);
        read.complete(refreshRead ? pairA.refreshToken : pairA.accessToken);
        await loginB;
        expect(
          await old,
          refreshRead
              ? isA<TokenRefreshFailure>().having(
                  (f) => f.type,
                  'type',
                  TokenRefreshFailureType.superseded,
                )
              : isA<DioException>(),
        );
        expect(h.app.requests, isEmpty);
        expect(h.refresh.requests, isEmpty);
        h.expectB();
      },
    );
  }

  for (final retry in [false, true]) {
    test(
      'transport guard blocks ${retry ? 'retry' : 'initial'} after async interceptor',
      () async {
        final h = Harness();
        final started = barrier();
        final release = barrier();
        h.dio.interceptors.add(
          InterceptorsWrapper(
            onRequest: (options, handler) async {
              if ((options.extra['mealio_auth_retried'] == true) == retry) {
                started.complete();
                await release.future;
              }
              handler.next(options);
            },
          ),
        );
        h.app.enqueue(rejected);
        h.refresh.enqueue(rotatedA);
        final old = outcome(
          h.api.patch<Object?>('/pantry/A', data: {'quantity': 7}),
        );
        await started.future;
        await h.storage.writeTokenPair(pairB);
        release.complete();
        expect(await old, isA<DioException>());
        expect(h.app.requests, hasLength(retry ? 1 : 0));
        expect(h.refresh.requests, hasLength(retry ? 1 : 0));
        h.expectB();
      },
    );
  }

  test('refresh transport guard blocks send after async preparation', () async {
    final h = Harness();
    final started = barrier();
    final release = barrier();
    h.refreshDio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          started.complete();
          await release.future;
          handler.next(options);
        },
      ),
    );
    final old = outcome(h.coordinator.refreshTokens());
    await started.future;
    await h.storage.writeTokenPair(pairB);
    release.complete();
    expect(
      await old,
      isA<TokenRefreshFailure>().having(
        (f) => f.type,
        'type',
        TokenRefreshFailureType.superseded,
      ),
    );
    expect(h.refresh.requests, isEmpty);
    h.expectB();
  });

  for (final response in [
    rotatedA,
    const FakeHttpResponse(statusCode: 200, body: {}),
    rejected,
  ]) {
    test(
      'late refresh ${response == rotatedA
          ? 'success'
          : response.statusCode == 200
          ? 'malformed'
          : '401'} preserves new login',
      () async {
        final h = Harness();
        final started = barrier();
        final release = barrier();
        h.refresh.responseHandler = (options) async {
          if (options.path == '/auth/logout') return ok;
          started.complete();
          await release.future;
          return response;
        };
        final old = outcome(h.coordinator.refreshTokens());
        await started.future;
        await h.storage.writeTokenPair(pairB);
        release.complete();
        expect(
          await old,
          isA<TokenRefreshFailure>().having(
            (f) => f.type,
            'type',
            TokenRefreshFailureType.superseded,
          ),
        );
        h.expectB();
        final revokes = h.refresh.requests.where(
          (r) => r.path == '/auth/logout',
        );
        expect(revokes, hasLength(response == rotatedA ? 1 : 0));
        if (revokes.isNotEmpty) {
          expect(revokes.single.data, {'refresh_token': 'rotated-refresh-A'});
        }
      },
    );
  }

  test(
    'B refresh does not join A; A finally cannot clear B single-flight',
    () async {
      final h = Harness();
      final startedA = barrier();
      final startedB = barrier();
      final releaseA = barrier();
      final releaseB = barrier();
      h.refresh.responseHandler = (options) async {
        if ((options.data as Map)['refresh_token'] == pairA.refreshToken) {
          startedA.complete();
          await releaseA.future;
          return rejected;
        }
        if (!startedB.isCompleted) startedB.complete();
        await releaseB.future;
        return rotatedB;
      };
      final a = outcome(h.coordinator.refreshTokens());
      await startedA.future;
      await h.storage.writeTokenPair(pairB);
      final b = h.coordinator.refreshTokens();
      await startedB.future;
      releaseA.complete();
      expect(await a, isA<TokenRefreshFailure>());
      final b2 = h.coordinator.refreshTokens();
      releaseB.complete();
      final results = await Future.wait([b, b2]);
      expect(results.map((p) => p.accessToken), everyElement('rotated-B'));
      expect(h.refresh.requests, hasLength(2));
      expect(h.invalidations, 0);
    },
  );

  test(
    'persistence failure cleanup after B login revokes only orphan A',
    () async {
      final h = Harness();
      h.storage.failAccessWrite = true;
      final revokeStarted = barrier();
      final releaseRevoke = barrier();
      h.refresh.responseHandler = (options) async {
        if (options.path == '/auth/refresh') return rotatedA;
        revokeStarted.complete();
        await releaseRevoke.future;
        return ok;
      };
      final old = outcome(h.coordinator.refreshTokens());
      await revokeStarted.future;
      h.storage.failAccessWrite = false;
      await h.storage.writeTokenPair(pairB);
      releaseRevoke.complete();
      expect(
        await old,
        isA<TokenRefreshFailure>().having(
          (f) => f.type,
          'type',
          TokenRefreshFailureType.superseded,
        ),
      );
      h.expectB();
      expect(h.refresh.requests.last.data, {
        'refresh_token': 'rotated-refresh-A',
      });
    },
  );

  for (final relogin in [false, true]) {
    test(
      'late protected success rejected after ${relogin ? 'same-account login' : 'logout'}',
      () async {
        final h = Harness();
        final started = barrier();
        final release = barrier();
        h.app.responseHandler = (_) async {
          started.complete();
          await release.future;
          return ok;
        };
        final old = outcome(h.api.get<Object?>('/auth/me'));
        await started.future;
        await h.storage.deleteTokenPair();
        if (relogin) {
          await h.storage.writeTokenPair(pairA); // Identical opaque strings.
        }
        release.complete();
        expect(
          await old,
          isA<DioException>().having(
            (e) => e.type,
            'type',
            DioExceptionType.cancel,
          ),
        );
        expect(h.app.requests, hasLength(1));
        expect(h.invalidations, 0);
        expect(h.storage.accessToken, relogin ? pairA.accessToken : isNull);
      },
    );
  }

  test(
    'account switch during initial 401 token read cannot refresh or replay B',
    () async {
      final h = Harness();
      final started = barrier();
      final read = Completer<String?>();
      addTearDown(() {
        if (!read.isCompleted) read.complete(null);
      });
      h.app.responseHandler = (_) {
        h.storage.accessReadStarted = started;
        h.storage.pendingRead = read;
        return rejected;
      };
      final old = outcome(
        h.api.patch<Object?>('/pantry/A', data: {'quantity': 7}),
      );
      await started.future;
      final login = h.storage.writeTokenPair(pairB);
      read.complete(pairB.accessToken);
      await login;
      expect(await old, isA<DioException>());
      expect(h.app.requests, hasLength(1));
      expect(h.refresh.requests, isEmpty);
      h.expectB();
    },
  );

  test(
    'partial refresh write fails after B intent without deleting queued B pair',
    () async {
      final h = Harness();
      final started = barrier();
      final write = Completer<void>();
      addTearDown(() {
        if (!write.isCompleted) write.complete();
      });
      h.storage.accessWriteStarted = started;
      h.storage.pendingAccessWrite = write;
      h.refresh.responseHandler = (options) =>
          options.path == '/auth/refresh' ? rotatedA : ok;
      final old = outcome(h.coordinator.refreshTokens());
      await started.future;
      h.storage.pendingAccessWrite = null;
      final login = h.storage.writeTokenPair(pairB);
      write.completeError(StateError('Synthetic platform write failure'));
      await login;
      expect(
        await old,
        isA<TokenRefreshFailure>().having(
          (f) => f.type,
          'type',
          TokenRefreshFailureType.superseded,
        ),
      );
      h.expectB();
      expect(h.refresh.requests.last.path, '/auth/logout');
      expect(h.refresh.requests.last.data, {
        'refresh_token': 'rotated-refresh-A',
      });
    },
  );

  for (final relogin in [false, true]) {
    test(
      'initial 401 after ${relogin ? 'same-token relogin' : 'logout'} cannot retry',
      () async {
        final h = Harness();
        final started = barrier();
        final release = barrier();
        h.app.responseHandler = (_) async {
          if (!started.isCompleted) started.complete();
          await release.future;
          return rejected;
        };
        final old = outcome(
          h.api.patch<Object?>('/pantry/A', data: {'quantity': 7}),
        );
        await started.future;
        await h.storage.deleteTokenPair();
        if (relogin) await h.storage.writeTokenPair(pairA);
        release.complete();
        expect(await old, isA<DioException>());
        expect(h.app.requests, hasLength(1));
        expect(h.refresh.requests, isEmpty);
        expect(h.invalidations, 0);
        expect(h.storage.accessToken, relogin ? pairA.accessToken : isNull);
      },
    );
  }
}
