<?php
// Configuration
$allowedExtensions = ['wav', 'mp3', 'csv', 'opus', 'raw'];
$uploadBaseDir    = 'uploads/';
$logFile          = 'upload_log.csv';
$apiKey           = '@YourPassword123';

// For raw→WAV conversion
define('RAW_SAMPLE_RATE',   88200);
define('RAW_CHANNELS',      1);
define('RAW_BITS_PER_SAMPLE', 16);

// ————————————————————————————————————————————————————————————————
// 1) AUTHENTICATE
// ————————————————————————————————————————————————————————————————
if (!isset($_POST['api_key']) || $_POST['api_key'] !== $apiKey) {
    http_response_code(403);
    echo "Forbidden: Invalid API key.";
    exit;
}

// ————————————————————————————————————————————————————————————————
// 2) SETUP METADATA & SESSION DIR
// ————————————————————————————————————————————————————————————————
$clientIp  = $_SERVER['REMOTE_ADDR'];
$timestamp = date('Y-m-d H:i:s');
$deviceId  = preg_replace('/[^A-Za-z0-9_\-\.]/','_', $_POST['device_id']  ?? 'unknown_device');
$sessionId = preg_replace('/[^A-Za-z0-9_\-\.]/','_', $_POST['session_id'] ?? 'unknown_session');

$sessionDir = $uploadBaseDir . "{$deviceId}_{$sessionId}/";
if (!is_dir($sessionDir) && !mkdir($sessionDir, 0775, true)) {
    http_response_code(500);
    echo "Error: Could not create session directory.";
    exit;
}

// ————————————————————————————————————————————————————————————————
// 3) HANDLE EACH UPLOADED FILE
// ————————————————————————————————————————————————————————————————
foreach ($_FILES as $field => $file) {
    $origName = basename($file['name']);
    $ext      = strtolower(pathinfo($origName, PATHINFO_EXTENSION));
    $size     = $file['size'];

    if ($file['error'] !== UPLOAD_ERR_OK) {
        echo "Error with upload of {$origName}: code {$file['error']}\n";
        continue;
    }

    if (!in_array($ext, $allowedExtensions)) {
        http_response_code(400);
        echo "Error: Invalid file type ({$ext}).";
        exit;
    }

    // ————————————————————————————————————————
    // A) WAV or RAW AUDIO CHUNK STREAMING
    // ————————————————————————————————————————
    if ($field === 'audio_chunk' && in_array($ext, ['wav','raw'])) {
        $streamPath = $sessionDir . 'stream.wav';
        $data       = file_get_contents($file['tmp_name']);

        // If RAW, data is pure PCM; if WAV, strip header
        if ($ext === 'wav') {
            // WAV: skip 44-byte header
            $pcmData = substr($data, 44);
        } else {
            // RAW: use full buffer as PCM
            $pcmData = $data;
        }

        // First chunk? write WAV header + PCM
        if (!file_exists($streamPath)) {
            // Build standard 44-byte WAV header with placeholders
            $byteRate    = RAW_SAMPLE_RATE * RAW_CHANNELS * (RAW_BITS_PER_SAMPLE/8);
            $blockAlign  = RAW_CHANNELS * (RAW_BITS_PER_SAMPLE/8);

            $header  = 'RIFF' . pack('V', 0) . 'WAVE';
            $header .= 'fmt ' . pack('V', 16);          // Subchunk1Size
            $header .= pack('v', 1);                    // PCM format
            $header .= pack('v', RAW_CHANNELS);
            $header .= pack('V', RAW_SAMPLE_RATE);
            $header .= pack('V', $byteRate);
            $header .= pack('v', $blockAlign);
            $header .= pack('v', RAW_BITS_PER_SAMPLE);
            $header .= 'data' . pack('V', 0);           // Subchunk2Size

            // Write header + first PCM block
            file_put_contents($streamPath, $header . $pcmData);
        } else {
            // Append PCM only
            file_put_contents($streamPath, $pcmData, FILE_APPEND);
        }

        // Patch WAV header sizes
        $totalSize = filesize($streamPath);
        $dataSize  = $totalSize - 44;
        $riffSize  = $totalSize - 8;

        $fp = fopen($streamPath, 'r+b');
        if ($fp) {
            // RIFF chunk size at offset 4
            fseek($fp, 4);
            fwrite($fp, pack('V', $riffSize));
            // data chunk size at offset 40
            fseek($fp, 40);
            fwrite($fp, pack('V', $dataSize));
            fclose($fp);
        }

        echo "Appended audio chunk ({$size} bytes). Total WAV size: {$totalSize} bytes\n";

        // Log
        $logEntry = [
            $timestamp,
            $clientIp,
            $deviceId,
            $sessionId,
            'stream.wav',
            $ext,
            $size,
            $streamPath
        ];
        file_put_contents($logFile, implode(',', $logEntry) . "\n", FILE_APPEND);

        continue;
    }

    // ————————————————————————————————————————
    // B) ONE-OFF FILES (CSV, MP3, OPUS, etc.)
    // ————————————————————————————————————————
    $dest = $sessionDir . $origName;
    if (!move_uploaded_file($file['tmp_name'], $dest)) {
        echo "Failed to upload: {$origName}\n";
        continue;
    }

    echo "Uploaded: {$origName}\n";

    // Log
    $logEntry = [
        $timestamp,
        $clientIp,
        $deviceId,
        $sessionId,
        $origName,
        $ext,
        $size,
        $dest
    ];
    file_put_contents($logFile, implode(',', $logEntry) . "\n", FILE_APPEND);
}
?>
