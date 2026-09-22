import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../models/models.dart';
import '../services/services.dart';
import '../widgets/widgets.dart';
import 'album_list_screen.dart';

enum HomeState { initial, loading, success, error }

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final ImagePicker _picker = ImagePicker();

  HomeState _state = HomeState.initial;
  Uint8List? _imageBytes;
  String? _imagePath;
  List<Label> _labels = [];
  LabelError? _error;
  String? _model;
  int? _latencyMs;
  AlbumEntry? _savedEntry;

  Future<void> _pickImage(ImageSource source) async {
    try {
      final XFile? picked = await _picker.pickImage(
        source: source,
        maxWidth: 2000,
        maxHeight: 2000,
      );

      if (picked == null) return;

      setState(() {
        _state = HomeState.loading;
        _imagePath = picked.path;
        _error = null;
      });

      final originalBytes = await picked.readAsBytes();
      final compressed = await CompressionService.compressImage(originalBytes);
      _imageBytes = compressed.bytes;

      await _requestLabels();
    } catch (e) {
      setState(() {
        _state = HomeState.error;
        _error = LabelError(code: 'compression', message: '圖片處理失敗：$e');
      });
    }
  }

  Future<void> _requestLabels() async {
    if (_imageBytes == null) return;

    setState(() => _state = HomeState.loading);

    final response = await LabelService.getLabels(_imageBytes!);

    if (response.ok && response.labels != null) {
      final labels = response.labels!.take(5).toList();

      try {
        final entry = await AlbumService.saveEntry(
          imageBytes: _imageBytes!,
          labels: labels,
        );
        setState(() {
          _state = HomeState.success;
          _labels = labels;
          _model = response.model;
          _latencyMs = response.latencyMs;
          _error = null;
          _savedEntry = entry;
        });
      } catch (e) {
        setState(() {
          _state = HomeState.success;
          _labels = labels;
          _model = response.model;
          _latencyMs = response.latencyMs;
          _error = null;
          _savedEntry = null;
        });
      }
    } else {
      setState(() {
        _state = HomeState.error;
        _error = response.error ?? LabelError(code: 'unknown', message: '未知錯誤');
        _labels = [];
        _savedEntry = null;
      });
    }
  }

  void _updateLabel(int index, Label label) {
    setState(() {
      _labels[index] = label;
    });
    _saveLabelsUpdate();
  }

  Future<void> _saveLabelsUpdate() async {
    if (_savedEntry != null) {
      try {
        final updated = _savedEntry!.copyWith(labels: _labels);
        await AlbumService.updateEntry(updated);
        _savedEntry = updated;
      } catch (_) {
        // Silent fail for auto-save
      }
    }
  }

  void _reset() {
    setState(() {
      _state = HomeState.initial;
      _imageBytes = null;
      _imagePath = null;
      _labels = [];
      _error = null;
      _model = null;
      _latencyMs = null;
      _savedEntry = null;
    });
  }

  void _openAlbum() {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (context) => const AlbumListScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('拍照學英文'),
        actions: [
          IconButton(
            icon: const Icon(Icons.photo_album),
            onPressed: _openAlbum,
            tooltip: '我的相簿',
          ),
          if (_state != HomeState.initial)
            IconButton(
              icon: const Icon(Icons.refresh),
              onPressed: _reset,
              tooltip: '重新開始',
            ),
        ],
      ),
      body: _buildBody(),
      bottomNavigationBar: _buildBottomBar(),
    );
  }

  Widget _buildBody() {
    switch (_state) {
      case HomeState.initial:
        return _buildInitialState();
      case HomeState.loading:
        return _buildLoadingState();
      case HomeState.success:
        return _buildSuccessState();
      case HomeState.error:
        return _buildErrorState();
    }
  }

  Widget _buildInitialState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.photo_library_outlined,
              size: 80,
              color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.5),
            ),
            const SizedBox(height: 24),
            const Text(
              '選擇一張喜歡的照片',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w500),
            ),
            const SizedBox(height: 8),
            const Text(
              '我們會辨識照片中的物品，幫你學英文',
              style: TextStyle(color: Colors.grey),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 32),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                FilledButton.icon(
                  onPressed: () => _pickImage(ImageSource.gallery),
                  icon: const Icon(Icons.photo_library),
                  label: const Text('相簿'),
                ),
                const SizedBox(width: 16),
                OutlinedButton.icon(
                  onPressed: () => _pickImage(ImageSource.camera),
                  icon: const Icon(Icons.camera_alt),
                  label: const Text('拍照'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLoadingState() {
    return Column(
      children: [
        if (_imagePath != null)
          Expanded(
            flex: 2,
            child: Container(
              margin: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(12),
                image: DecorationImage(
                  image: FileImage(File(_imagePath!)),
                  fit: BoxFit.contain,
                ),
              ),
            ),
          ),
        const Expanded(
          child: Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                CircularProgressIndicator(),
                SizedBox(height: 16),
                Text('正在辨識照片...'),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildSuccessState() {
    return Column(
      children: [
        if (_imagePath != null)
          Container(
            height: 200,
            margin: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              image: DecorationImage(
                image: FileImage(File(_imagePath!)),
                fit: BoxFit.cover,
              ),
            ),
          ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Row(
            children: [
              const Text(
                '辨識結果',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const Spacer(),
              if (_model != null)
                Text(
                  _model!,
                  style: TextStyle(fontSize: 12, color: Colors.grey[600]),
                ),
              if (_latencyMs != null) ...[
                const SizedBox(width: 8),
                Text(
                  '${_latencyMs}ms',
                  style: TextStyle(fontSize: 12, color: Colors.grey[600]),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 8),
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.only(bottom: 16),
            itemCount: _labels.length,
            itemBuilder: (context, index) {
              return LabelCard(
                label: _labels[index],
                index: index,
                onChanged: (label) => _updateLabel(index, label),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildErrorState() {
    return Column(
      children: [
        if (_imagePath != null)
          Container(
            height: 200,
            margin: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              image: DecorationImage(
                image: FileImage(File(_imagePath!)),
                fit: BoxFit.cover,
              ),
            ),
          ),
        Expanded(
          child: ErrorView(
            error: _error!,
            onRetry: _requestLabels,
          ),
        ),
      ],
    );
  }

  Widget _buildBottomBar() {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        border: Border(
          top: BorderSide(color: Colors.grey[200]!),
        ),
      ),
      child: SafeArea(
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              ConfigService.shouldUseMock ? Icons.science : Icons.cloud,
              size: 16,
              color: Colors.grey[600],
            ),
            const SizedBox(width: 4),
            Text(
              ConfigService.configSummary,
              style: TextStyle(
                fontSize: 12,
                color: Colors.grey[600],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
