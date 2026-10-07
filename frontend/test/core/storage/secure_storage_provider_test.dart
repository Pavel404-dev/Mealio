import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/auth/auth_token_pair.dart';

import '../../helpers/auth_test_fakes.dart';

void main() {
  const pair = AuthTokenPair(
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
  );

  test('access token write read and delete are supported', () async {
    final storage = FakeSecureStorageService();

    await storage.writeAccessToken('access-token');
    expect(await storage.readAccessToken(), 'access-token');

    await storage.deleteAccessToken();
    expect(await storage.readAccessToken(), isNull);
  });

  test('refresh token write read and delete are supported', () async {
    final storage = FakeSecureStorageService();

    await storage.writeRefreshToken('refresh-token');
    expect(await storage.readRefreshToken(), 'refresh-token');

    await storage.deleteRefreshToken();
    expect(await storage.readRefreshToken(), isNull);
  });

  test('writeTokenPair stores both credentials', () async {
    final storage = FakeSecureStorageService();

    await storage.writeTokenPair(pair);

    expect(storage.accessToken, 'access-token');
    expect(storage.refreshToken, 'refresh-token');
  });

  test('deleteTokenPair attempts to clear both credentials', () async {
    final storage = FakeSecureStorageService(
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
    );

    await storage.deleteTokenPair();

    expect(storage.accessToken, isNull);
    expect(storage.refreshToken, isNull);
    expect(storage.deleteCount, 1);
    expect(storage.refreshDeleteCount, 1);
  });

  test('partial token pair write failure cleans both credentials', () async {
    final storage = FakeSecureStorageService(
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
      failAccessWrite: true,
    );

    await expectLater(storage.writeTokenPair(pair), throwsStateError);

    expect(storage.accessToken, isNull);
    expect(storage.refreshToken, isNull);
    expect(storage.refreshWriteCount, 1);
    expect(storage.writeCount, 1);
  });

  test('conditional replacement only updates the matching session', () async {
    final storage = FakeSecureStorageService(
      accessToken: 'old-access',
      refreshToken: 'old-refresh',
    );

    final mismatch = await storage.replaceTokenPairIfRefreshTokenMatches(
      expectedRefreshToken: 'another-refresh',
      pair: pair,
    );

    expect(mismatch, isFalse);
    expect(storage.accessToken, 'old-access');
    expect(storage.refreshToken, 'old-refresh');

    final replaced = await storage.replaceTokenPairIfRefreshTokenMatches(
      expectedRefreshToken: 'old-refresh',
      pair: pair,
    );

    expect(replaced, isTrue);
    expect(storage.accessToken, 'access-token');
    expect(storage.refreshToken, 'refresh-token');
  });

  test(
    'deleteTokenPair waits for an in-progress pair write and wins',
    () async {
      final storage = FakeSecureStorageService(
        accessToken: 'old-access',
        refreshToken: 'old-refresh',
      );
      final accessWriteStarted = Completer<void>();
      final releaseAccessWrite = Completer<void>();

      storage.accessWriteStarted = accessWriteStarted;
      storage.pendingAccessWrite = releaseAccessWrite;

      final writeFuture = storage.writeTokenPair(pair);

      await accessWriteStarted.future;

      // The refresh credential has already been written, while the access
      // credential is intentionally paused inside the same pair mutation.
      expect(storage.refreshToken, 'refresh-token');
      expect(storage.accessToken, 'old-access');

      final deleteFuture = storage.deleteTokenPair();

      // Give the queued delete an opportunity to run. It must remain blocked
      // until the complete token-pair write releases the mutation queue.
      await Future<void>.delayed(Duration.zero);

      expect(storage.deleteCount, 0);
      expect(storage.refreshDeleteCount, 0);

      releaseAccessWrite.complete();

      await writeFuture;
      await deleteFuture;

      expect(storage.accessToken, isNull);
      expect(storage.refreshToken, isNull);
      expect(storage.deleteCount, 1);
      expect(storage.refreshDeleteCount, 1);
    },
  );

  test(
    'deleteTokenPair still attempts refresh deletion after access failure',
    () async {
      final storage = FakeSecureStorageService(
        accessToken: 'access-token',
        refreshToken: 'refresh-token',
        failAccessDelete: true,
      );

      await expectLater(storage.deleteTokenPair(), throwsStateError);

      expect(storage.refreshToken, isNull);
      expect(storage.deleteCount, 1);
      expect(storage.refreshDeleteCount, 1);
    },
  );

  test(
    'queued conditional cleanup checks lifetime after an in-progress rotation',
    () async {
      final storage = FakeSecureStorageService(
        accessToken: 'old-access',
        refreshToken: 'old-refresh',
      );
      final lifetime = storage.sessionLifetime;
      final started = Completer<void>();
      final release = Completer<void>();
      addTearDown(() {
        if (!release.isCompleted) release.complete();
      });
      storage.accessWriteStarted = started;
      storage.pendingAccessWrite = release;
      final rotation = storage.replaceTokenPairIfRefreshTokenMatches(
        expectedRefreshToken: 'old-refresh',
        pair: pair,
        sessionLifetime: lifetime,
      );
      await started.future;
      var invalidations = 0;
      final cleanup = storage.deleteTokenPairIfSessionMatches(
        lifetime,
        onDeleted: () => invalidations++,
      );
      final login = storage.writeTokenPair(
        const AuthTokenPair(accessToken: 'B', refreshToken: 'B-refresh'),
      );
      release.complete();
      expect(await rotation, isFalse);
      expect(await cleanup, isFalse);
      await login;
      expect(storage.accessToken, 'B');
      expect(storage.refreshToken, 'B-refresh');
      expect(invalidations, 0);
      expect(storage.deleteCount, 0);
    },
  );

  test(
    'in-progress conditional delete cannot publish invalidation for pending login',
    () async {
      final storage = FakeSecureStorageService(
        accessToken: 'old-access',
        refreshToken: 'old-refresh',
      );
      final started = Completer<void>();
      final release = Completer<void>();
      addTearDown(() {
        if (!release.isCompleted) release.complete();
      });
      storage.accessDeleteStarted = started;
      storage.pendingAccessDelete = release;
      var invalidations = 0;
      final cleanup = storage.deleteTokenPairIfSessionMatches(
        storage.sessionLifetime,
        onDeleted: () => invalidations++,
      );
      await started.future;
      final login = storage.writeTokenPair(pair);
      release.complete();
      await cleanup;
      await login;
      expect(storage.accessToken, pair.accessToken);
      expect(storage.refreshToken, pair.refreshToken);
      expect(invalidations, 0);
    },
  );

  test(
    'session read waits for complete login pair and never uses old access',
    () async {
      final storage = FakeSecureStorageService(
        accessToken: 'old-access',
        refreshToken: 'old-refresh',
      );
      final started = Completer<void>();
      final release = Completer<void>();
      addTearDown(() {
        if (!release.isCompleted) release.complete();
      });
      storage.accessWriteStarted = started;
      storage.pendingAccessWrite = release;
      final oldLifetime = storage.sessionLifetime;
      final login = storage.writeTokenPair(pair);
      expect(storage.sessionLifetime, isNot(oldLifetime));
      await started.future;
      final read = storage.readSessionAccessToken(storage.sessionLifetime);
      expect(storage.readCount, 0);
      release.complete();
      await login;
      expect(await read, pair.accessToken);
    },
  );

  test(
    'conditional replacement rechecks lifetime after refresh-token read',
    () async {
      final storage = FakeSecureStorageService(
        accessToken: 'old-access',
        refreshToken: 'same-refresh',
      );
      final started = Completer<void>();
      final read = Completer<String?>();
      addTearDown(() {
        if (!read.isCompleted) read.complete(null);
      });
      storage.refreshReadStarted = started;
      storage.pendingRefreshRead = read;
      final rotation = storage.replaceTokenPairIfRefreshTokenMatches(
        expectedRefreshToken: 'same-refresh',
        pair: pair,
      );
      await started.future;
      final login = storage.writeTokenPair(
        const AuthTokenPair(accessToken: 'B', refreshToken: 'same-refresh'),
      );
      read.complete('same-refresh');
      expect(await rotation, isFalse);
      await login;
      expect(storage.accessToken, 'B');
      expect(storage.writeCount, 1);
    },
  );
}
