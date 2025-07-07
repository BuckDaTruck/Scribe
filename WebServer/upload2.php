<?php
$allowedExtensions = ['wav', 'mp3', 'csv', 'opus'];
$uploadBaseDir  = 'uploads/';
$logFile        = 'upload_log.csv';
$apiKey         = '@YourPassword123';

if (!isset($_POST['api_key']) || $_POST['api_key'] !== $apiKey) {
    http_response_code(403);
    echo "Forbidden: Invalid API key.";
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo "Method not allowed. Please use POST for uploads.";
    exit;
}

// Common metadata
$clientIp  = $_SERVER['REMOTE_ADDR'];
$timestamp = date('Y-m-d H:i:s');
$deviceId  = preg_replace('/[^a-zA-Z0-9_\-\.]/', '_', $_POST['device_id']  ?? 'unknown_device');
$sessionId = preg_replace('/[^a-zA-Z0-9_\-\.]/', '_', $_POST['session_id'] ?? 'unknown_session');

$sessionDir = $uploadBaseDir . "{$deviceId}_{$sessionId}/";
if (!is_dir($sessionDir) && !mkdir($sessionDir, 0775, true)) {
    http_response_code(500);
    echo "Error: Could not create session directory.";
    exit;
}

foreach ($_FILES as $field => $file) {
    $origName = basename($file['name']);
    $ext      = strtolower(pathinfo($origName, PATHINFO_EXTENSION));
    $size     = $file['size'];

    if (!in_array($ext, $allowedExtensions)) {
        http_response_code(400);
        echo "Error: Invalid file type ($ext).";
        exit;
    }

    // ** 1) Continuous WAV streaming **
    if ($field === 'audio_chunk' && $ext === 'wav') {
        $streamPath = $sessionDir . 'stream.wav';
        $data       = file_get_contents($file['tmp_name']);
        if ($data === false || file_put_contents($streamPath, $data, FILE_APPEND) === false) {
            http_response_code(500);
            echo "Error: Failed to append audio chunk.";
        } else {
            echo "Appended audio chunk.\n";
            // Log the chunk append
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
        }
        continue;
    }

    // ** 2) One‐off file uploads (CSV, MP3, OPUS, etc.) **
    $dest = $sessionDir . $origName;
    if (!move_uploaded_file($file['tmp_name'], $dest)) {
        echo "Failed to upload: $origName\n";
        continue;
    }

    echo "Uploaded: $origName\n";

    // Log the upload
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
