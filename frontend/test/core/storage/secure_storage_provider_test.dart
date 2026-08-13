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
}
