<?php
$allowedExtensions = ['wav', 'mp3', 'csv','opus'];
$uploadBaseDir = 'uploads/';
$logFile = 'upload_log.csv';
$apiKey = '@YourPassword123';

if (!isset($_POST['api_key']) || $_POST['api_key'] !== $apiKey) {
    http_response_code(403);
    echo "Forbidden: Invalid API key.";
    exit;
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $clientIp = $_SERVER['REMOTE_ADDR'];
    $timestamp = date('Y-m-d H:i:s');
    $timeFormatted = date('H-i_m-d-y');

    // Metadata
    $deviceId = preg_replace('/[^a-zA-Z0-9_\-\.]/', '_', $_POST['device_id'] ?? 'unknown_device');
    $sessionId = preg_replace('/[^a-zA-Z0-9_\-\.]/', '_', $_POST['session_id'] ?? 'unknown_session');

    $folderName = "{$deviceId}_{$sessionId}";
    $sessionDir = $uploadBaseDir . $folderName . '/';
    if (!is_dir($sessionDir)) {
        mkdir($sessionDir, 0775, true);
    }

    foreach ($_FILES as $key => $file) {
        $fileName = basename($file['name']);
        $ext = strtolower(pathinfo($fileName, PATHINFO_EXTENSION));
        $size = $file['size'];

        if (!in_array($ext, $allowedExtensions)) {
            http_response_code(400);
            echo "Error: Invalid file type ($ext).";
            exit;
        }

        $destination = $sessionDir . $fileName;
        if (move_uploaded_file($file['tmp_name'], $destination)) {
            echo "Uploaded: $fileName\n";

            $logEntry = [
                $timestamp,
                $clientIp,
                $deviceId,
                $sessionId,
                $fileName,
                $ext,
                $size,
                $destination
            ];
            $logLine = implode(",", $logEntry) . "\n";
            file_put_contents($logFile, $logLine, FILE_APPEND);
        } else {
            echo "Failed to upload: $fileName\n";
        }
    }
} else {
    http_response_code(405);
    echo "Method not allowed.";
}
?>
