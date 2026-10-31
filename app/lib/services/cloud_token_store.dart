import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Where the account login token lives (card #910). On a phone it is the iOS
/// Keychain / Android Keystore, never the settings box or a backup file.
abstract class CloudTokenStore {
  Future<String> read();
  Future<void> write(String token);
  Future<void> delete();
}

class KeychainTokenStore implements CloudTokenStore {
  static const _key = 'accountToken';
  final FlutterSecureStorage _storage;

  const KeychainTokenStore(
      [this._storage = const FlutterSecureStorage(
          iOptions: IOSOptions(
              accessibility: KeychainAccessibility.first_unlock_this_device))]);

  @override
  Future<String> read() async => await _storage.read(key: _key) ?? '';

  @override
  Future<void> write(String token) => _storage.write(key: _key, value: token);

  @override
  Future<void> delete() => _storage.delete(key: _key);
}

class MemoryTokenStore implements CloudTokenStore {
  String value;
  MemoryTokenStore([this.value = '']);

  @override
  Future<String> read() async => value;

  @override
  Future<void> write(String token) async => value = token;

  @override
  Future<void> delete() async => value = '';
}
