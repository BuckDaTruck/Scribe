<?php
// Configuration
$uploadDir = 'uploads/';
$allowedAudioTypes = ['mp3', 'wav', 'mp4', 'm4a', 'flac', 'ogg'];

// Handle AJAX requests
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    header('Content-Type: application/json');
    
    if (isset($_POST['action'])) {
        switch ($_POST['action']) {
            case 'rename':
                $oldName = $_POST['oldName'];
                $newName = $_POST['newName'];
                
                if (is_dir($uploadDir . $oldName) && !empty($newName)) {
                    $success = rename($uploadDir . $oldName, $uploadDir . $newName);
                    echo json_encode(['success' => $success]);
                } else {
                    echo json_encode(['success' => false, 'error' => 'Invalid folder name']);
                }
                break;
                
            case 'transcribe':
                $folderName = $_POST['folderName'];
                $audioFile = $_POST['audioFile'];
                $audioPath = $uploadDir . $folderName . '/' . $audioFile;
                
                if (file_exists($audioPath)) {
                    $transcription = transcribeAudio($audioPath);
                    
                    // Save transcription to file
                    $transcriptFile = saveTranscription($folderName, $audioFile, $transcription);
                    
                    echo json_encode([
                        'success' => true, 
                        'transcription' => $transcription,
                        'saved_file' => $transcriptFile
                    ]);
                } else {
                    echo json_encode(['success' => false, 'error' => 'Audio file not found']);
                }
                break;
        }
    }
    exit;
}

// Function to transcribe audio using AssemblyAI (free tier)
function transcribeAudio($audioPath) {
    // You'll need to replace 'YOUR_ASSEMBLYAI_API_KEY' with your actual AssemblyAI API key
    // Sign up at https://www.assemblyai.com/ for free API key
    $apiKey = '8b58645e0193407f87c396346e54c919';
    
    // Step 1: Upload the audio file
    $uploadUrl = uploadAudioFile($audioPath, $apiKey);
    if (!$uploadUrl) {
        return 'Failed to upload audio file';
    }
    
    // Step 2: Submit for transcription
    $transcriptId = submitTranscription($uploadUrl, $apiKey);
    if (!$transcriptId) {
        return 'Failed to submit for transcription';
    }
    
    // Step 3: Poll for completion (simplified - in production you'd want better polling)
    $maxAttempts = 30; // 30 seconds max wait
    for ($i = 0; $i < $maxAttempts; $i++) {
        sleep(1);
        $result = getTranscriptionResult($transcriptId, $apiKey);
        if ($result['status'] === 'completed') {
            return $result['text'];
        } elseif ($result['status'] === 'error') {
            return 'Transcription error: ' . $result['error'];
        }
    }
    
    return 'Transcription timed out - please try again';
}

function uploadAudioFile($audioPath, $apiKey) {
    $curl = curl_init();
    
    curl_setopt_array($curl, [
        CURLOPT_URL => "https://api.assemblyai.com/v2/upload",
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_HTTPHEADER => [
            "Authorization: " . $apiKey,
            "Content-Type: application/octet-stream"
        ],
        CURLOPT_POSTFIELDS => file_get_contents($audioPath)
    ]);
    
    $response = curl_exec($curl);
    $httpCode = curl_getinfo($curl, CURLINFO_HTTP_CODE);
    curl_close($curl);
    
    if ($httpCode === 200) {
        $data = json_decode($response, true);
        return $data['upload_url'] ?? null;
    }
    
    return null;
}

function submitTranscription($audioUrl, $apiKey) {
    $curl = curl_init();
    
    curl_setopt_array($curl, [
        CURLOPT_URL => "https://api.assemblyai.com/v2/transcript",
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_HTTPHEADER => [
            "Authorization: " . $apiKey,
            "Content-Type: application/json"
        ],
        CURLOPT_POSTFIELDS => json_encode([
            'audio_url' => $audioUrl
        ])
    ]);
    
    $response = curl_exec($curl);
    $httpCode = curl_getinfo($curl, CURLINFO_HTTP_CODE);
    curl_close($curl);
    
    if ($httpCode === 200) {
        $data = json_decode($response, true);
        return $data['id'] ?? null;
    }
    
    return null;
}

function getTranscriptionResult($transcriptId, $apiKey) {
    $curl = curl_init();
    
    curl_setopt_array($curl, [
        CURLOPT_URL => "https://api.assemblyai.com/v2/transcript/" . $transcriptId,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => [
            "Authorization: " . $apiKey
        ]
    ]);
    
    $response = curl_exec($curl);
    $httpCode = curl_getinfo($curl, CURLINFO_HTTP_CODE);
    curl_close($curl);
    
    if ($httpCode === 200) {
        $data = json_decode($response, true);
        return [
            'status' => $data['status'],
            'text' => $data['text'] ?? '',
            'error' => $data['error'] ?? ''
        ];
    }
    
    return ['status' => 'error', 'error' => 'API request failed'];
}

// Function to save transcription to file
function saveTranscription($folderName, $audioFile, $transcription) {
    global $uploadDir;
    
    // Simple filename - just "transcript.txt"
    $transcriptFile = 'transcript.txt';
    $transcriptPath = $uploadDir . $folderName . '/' . $transcriptFile;
    
    // Create content with metadata
    $content = "Transcription of: " . $audioFile . "\n";
    $content .= "Generated on: " . date('Y-m-d H:i:s') . "\n";
    $content .= "=" . str_repeat("=", 50) . "\n\n";
    $content .= $transcription;
    
    // Save to file
    if (file_put_contents($transcriptPath, $content) !== false) {
        return $transcriptFile;
    }
    
    return false;
}

// Get folders and their contents
function getFolders($dir) {
    $folders = [];
    if (is_dir($dir)) {
        $items = scandir($dir);
        foreach ($items as $item) {
            if ($item !== '.' && $item !== '..' && is_dir($dir . $item)) {
                $folderContents = scandir($dir . $item);
                $audioFiles = [];
                $csvFiles = [];
                $transcriptFiles = [];
                
                foreach ($folderContents as $file) {
                    if ($file !== '.' && $file !== '..') {
                        $ext = strtolower(pathinfo($file, PATHINFO_EXTENSION));
                        if (in_array($ext, $GLOBALS['allowedAudioTypes'])) {
                            $audioFiles[] = $file;
                        } elseif ($ext === 'csv') {
                            $csvFiles[] = $file;
                        } elseif ($ext === 'txt' && $file === 'transcript.txt') {
                            $transcriptFiles[] = $file;
                        }
                    }
                }
                
                $folders[] = [
                    'name' => $item,
                    'audioFiles' => $audioFiles,
                    'csvFiles' => $csvFiles,
                    'transcriptFiles' => $transcriptFiles
                ];
            }
        }
    }
    return $folders;
}

$folders = getFolders($uploadDir);
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Audio Folder Manager</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        
        .container {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        h1 {
            color: #333;
            text-align: center;
            margin-bottom: 30px;
        }
        
        .folder-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
        }
        
        .folder-card {
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            background: #fafafa;
        }
        
        .folder-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
        }
        
        .folder-name {
            font-weight: bold;
            flex-grow: 1;
            padding: 5px;
            border: 1px solid transparent;
            border-radius: 4px;
            background: transparent;
        }
        
        .folder-name:hover {
            border-color: #007cba;
            background: white;
        }
        
        .rename-btn {
            background: #007cba;
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        
        .rename-btn:hover {
            background: #005a87;
        }
        
        .file-section {
            margin-bottom: 15px;
        }
        
        .file-section h4 {
            margin: 0 0 10px 0;
            color: #555;
        }
        
        .audio-controls {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 10px;
        }
        
        .audio-player {
            flex-grow: 1;
        }
        
        .transcribe-btn {
            background: #28a745;
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        
        .transcribe-btn:hover {
            background: #218838;
        }
        
        .transcribe-btn:disabled {
            background: #6c757d;
            cursor: not-allowed;
        }
        
        .transcription-result {
            margin-top: 10px;
            padding: 10px;
            background: #e9ecef;
            border-left: 4px solid #007cba;
            border-radius: 4px;
            font-size: 14px;
            line-height: 1.4;
        }
        
        .file-list {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        
        .file-list li {
            padding: 5px 0;
            border-bottom: 1px solid #eee;
        }
        
        .file-list li:last-child {
            border-bottom: none;
        }
        
        .no-files {
            color: #999;
            font-style: italic;
        }
        
        .loading {
            display: none;
            color: #007cba;
        }
        
        .error {
            color: #dc3545;
            font-size: 14px;
            margin-top: 5px;
        }
        
        .success {
            color: #28a745;
            font-size: 14px;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Audio Folder Manager</h1>
        
        <?php if (empty($folders)): ?>
            <p class="no-files">No folders found in the uploads directory.</p>
        <?php else: ?>
            <div class="folder-grid">
                <?php foreach ($folders as $folder): ?>
                    <div class="folder-card">
                        <div class="folder-header">
                            <input type="text" class="folder-name" value="<?php echo htmlspecialchars($folder['name']); ?>" data-original="<?php echo htmlspecialchars($folder['name']); ?>">
                            <button class="rename-btn" onclick="renameFolder(this)">Rename</button>
                        </div>
                        
                        <div class="file-section">
                            <h4>Audio Files</h4>
                            <?php if (!empty($folder['audioFiles'])): ?>
                                <?php foreach ($folder['audioFiles'] as $audioFile): ?>
                                    <div class="audio-controls">
                                        <audio class="audio-player" controls>
                                            <source src="<?php echo $uploadDir . $folder['name'] . '/' . $audioFile; ?>" type="audio/<?php echo pathinfo($audioFile, PATHINFO_EXTENSION); ?>">
                                            Your browser does not support the audio element.
                                        </audio>
                                        <button class="transcribe-btn" onclick="transcribeAudio('<?php echo $folder['name']; ?>', '<?php echo $audioFile; ?>', this)">
                                            Transcribe
                                        </button>
                                    </div>
                                    <div class="loading">Transcribing...</div>
                                    <div class="transcription-result" style="display: none;"></div>
                                <?php endforeach; ?>
                            <?php else: ?>
                                <p class="no-files">No audio files found</p>
                            <?php endif; ?>
                        </div>
                        
                        <div class="file-section">
                            <h4>Transcript Files</h4>
                            <?php if (!empty($folder['transcriptFiles'])): ?>
                                <ul class="file-list">
                                    <?php foreach ($folder['transcriptFiles'] as $transcriptFile): ?>
                                        <li>
                                            <a href="<?php echo $uploadDir . $folder['name'] . '/' . $transcriptFile; ?>" target="_blank">
                                                <?php echo htmlspecialchars($transcriptFile); ?>
                                            </a>
                                        </li>
                                    <?php endforeach; ?>
                                </ul>
                            <?php else: ?>
                                <p class="no-files">No transcript files found</p>
                            <?php endif; ?>
                        </div>
                        
                        <div class="file-section">
                            <h4>CSV Files</h4>
                            <?php if (!empty($folder['csvFiles'])): ?>
                                <ul class="file-list">
                                    <?php foreach ($folder['csvFiles'] as $csvFile): ?>
                                        <li>
                                            <a href="<?php echo $uploadDir . $folder['name'] . '/' . $csvFile; ?>" target="_blank">
                                                <?php echo htmlspecialchars($csvFile); ?>
                                            </a>
                                        </li>
                                    <?php endforeach; ?>
                                </ul>
                            <?php else: ?>
                                <p class="no-files">No CSV files found</p>
                            <?php endif; ?>
                        </div>
                    </div>
                <?php endforeach; ?>
            </div>
        <?php endif; ?>
    </div>

    <script>
        function renameFolder(button) {
            const input = button.parentElement.querySelector('.folder-name');
            const originalName = input.dataset.original;
            const newName = input.value.trim();
            
            if (newName === originalName) {
                return;
            }
            
            if (newName === '') {
                alert('Folder name cannot be empty');
                input.value = originalName;
                return;
            }
            
            button.disabled = true;
            button.textContent = 'Renaming...';
            
            const formData = new FormData();
            formData.append('action', 'rename');
            formData.append('oldName', originalName);
            formData.append('newName', newName);
            
            fetch(window.location.href, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    input.dataset.original = newName;
                    showMessage(button, 'Renamed successfully!', 'success');
                    // Update audio source paths and transcript links
                    const audioElements = button.closest('.folder-card').querySelectorAll('audio source');
                    audioElements.forEach(source => {
                        const currentSrc = source.src;
                        const newSrc = currentSrc.replace('/' + originalName + '/', '/' + newName + '/');
                        source.src = newSrc;
                        source.parentElement.load();
                    });
                    
                    // Update transcript file links
                    const transcriptLinks = button.closest('.folder-card').querySelectorAll('a[href*="transcript.txt"]');
                    transcriptLinks.forEach(link => {
                        const currentHref = link.href;
                        const newHref = currentHref.replace('/' + originalName + '/', '/' + newName + '/');
                        link.href = newHref;
                    });
                } else {
                    input.value = originalName;
                    showMessage(button, 'Failed to rename folder', 'error');
                }
            })
            .catch(error => {
                input.value = originalName;
                showMessage(button, 'Error: ' + error.message, 'error');
            })
            .finally(() => {
                button.disabled = false;
                button.textContent = 'Rename';
            });
        }
        
        function transcribeAudio(folderName, audioFile, button) {
            const controls = button.parentElement;
            const loading = controls.nextElementSibling;
            const result = loading.nextElementSibling;
            
            button.disabled = true;
            button.textContent = 'Transcribing...';
            loading.style.display = 'block';
            result.style.display = 'none';
            
            const formData = new FormData();
            formData.append('action', 'transcribe');
            formData.append('folderName', folderName);
            formData.append('audioFile', audioFile);
            
            fetch(window.location.href, {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    result.textContent = data.transcription;
                    result.style.display = 'block';
                    
                    // Show success message about saved file
                    if (data.saved_file) {
                        showMessage(button, 'Transcription saved as: ' + data.saved_file, 'success');
                        // Refresh the page after 2 seconds to show the new transcript file
                        setTimeout(() => {
                            window.location.reload();
                        }, 2000);
                    }
                } else {
                    result.textContent = 'Transcription failed: ' + (data.error || 'Unknown error');
                    result.style.display = 'block';
                    result.style.borderLeftColor = '#dc3545';
                }
            })
            .catch(error => {
                result.textContent = 'Error: ' + error.message;
                result.style.display = 'block';
                result.style.borderLeftColor = '#dc3545';
            })
            .finally(() => {
                button.disabled = false;
                button.textContent = 'Transcribe';
                loading.style.display = 'none';
            });
        }
        
        function showMessage(element, message, type) {
            const messageDiv = document.createElement('div');
            messageDiv.className = type;
            messageDiv.textContent = message;
            element.parentElement.appendChild(messageDiv);
            
            setTimeout(() => {
                messageDiv.remove();
            }, 3000);
        }
    </script>
</body>
</html>