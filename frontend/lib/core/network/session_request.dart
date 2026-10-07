import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../storage/secure_storage_provider.dart';

const sessionLifetimeKey = 'mealio_session_lifetime';

DioException supersededRequest(RequestOptions options) => DioException(
  requestOptions: options,
  type: DioExceptionType.cancel,
  error: const SessionSuperseded(),
);

/// The final synchronous check after Dio's async interceptors/transformer.
/// Requests already handed to the underlying transport cannot be unsent.
class SessionHttpClientAdapter implements HttpClientAdapter {
  SessionHttpClientAdapter(this.delegate, this.storage);

  final HttpClientAdapter delegate;
  final SecureStorageService storage;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) {
    final lifetime = options.extra[sessionLifetimeKey];
    if (lifetime is int && !storage.ownsSession(lifetime)) {
      return Future.error(supersededRequest(options));
    }
    return delegate.fetch(options, requestStream, cancelFuture);
  }

  @override
  void close({bool force = false}) => delegate.close(force: force);
}
