<?php
$allowedExtensions = ['wav', 'mp3', 'csv','opus'];
$uploadDir = 'uploads/';
$logFile = 'upload_log.csv';
$apiKey = '@YourPassword123'; // Set securely

// Check API key
if (!isset($_POST['api_key']) || $_POST['api_key'] !== $apiKey) {
    http_response_code(403);
    echo "Forbidden: Invalid API key.";
    exit;
}

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $clientIp = $_SERVER['REMOTE_ADDR'];
    $timestamp = date('Y-m-d H:i:s');

    foreach ($_FILES as $key => $file) {
        $fileName = basename($file['name']);
        $ext = strtolower(pathinfo($fileName, PATHINFO_EXTENSION));
        $size = $file['size'];

        // Validate extension
        if (!in_array($ext, $allowedExtensions)) {
            http_response_code(400);
            echo "Error: Invalid file type ($ext).";
            exit;
        }

        // Save file
        $destination = $uploadDir . $fileName;
        if (move_uploaded_file($file['tmp_name'], $destination)) {
            echo "Uploaded: $fileName\n";

            // Append log
            $logEntry = [
                $timestamp,
                $clientIp,
                $fileName,
                $ext,
                $size
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
