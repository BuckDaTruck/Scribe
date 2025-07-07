<?php
$allowedExtensions = ['wav','mp3','csv','opus'];
$uploadBaseDir    = 'uploads/';
$logFile          = 'upload_log.csv';
$apiKey           = '@YourPassword123';

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
    // A) WAV CHUNK STREAMING
    // ————————————————————————————————————————
    if ($field === 'audio_chunk' && $ext === 'wav') {
        $streamPath = $sessionDir . 'stream.wav';
        $data       = file_get_contents($file['tmp_name']);

        // First chunk? write full header+data
        if (!file_exists($streamPath)) {
            file_put_contents($streamPath, $data);
        } else {
            // Strip the 44-byte header, append only PCM data
            $pcmData = substr($data, 44);
            file_put_contents($streamPath, $pcmData, FILE_APPEND);
        }

        // Now fix up the WAV header sizes
        $totalSize = filesize($streamPath);
        $dataSize  = $totalSize - 44;       // PCM bytes
        $riffSize  = $totalSize - 8;        // RIFF chunk size = fileSize - 8

        // Open for read+write and patch header fields
        $fp = fopen($streamPath, 'r+b');
        if ($fp) {
            // At offset 4, 4-byte little-endian RIFF size
            fseek($fp, 4);
            fwrite($fp, pack('V', $riffSize));
            // At offset 40, 4-byte little-endian data-chunk size
            fseek($fp, 40);
            fwrite($fp, pack('V', $dataSize));
            fclose($fp);
        }

        echo "Appended WAV chunk ({$size} bytes). Total: {$totalSize} bytes\n";

        // Log it
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

    // Log standard file upload
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
