<?php
// Test script to debug the bootstrap status
require_once '../server/src/db.php';
require_once '../server/src/SystemController.php';

echo "Testing SystemController::getBootstrapStatus()...\n\n";

$status = SystemController::getBootstrapStatus();
echo "Result:\n";
var_dump($status);

echo "\nJSON encoded:\n";
echo json_encode($status);

echo "\n\nDirect database query:\n";
try {
    $pdo = DB::conn();
    $stmt = $pdo->prepare("SELECT patch_name, success FROM patches WHERE patch_name = 'bootstrap_complete'");
    $stmt->execute();
    $result = $stmt->fetch();
    echo "Raw result:\n";
    var_dump($result);
    
    if ($result) {
        echo "\nSuccess field value: ";
        var_dump($result['success']);
        echo "Type: " . gettype($result['success']) . "\n";
        echo "Truthy check: " . ($result['success'] ? 'true' : 'false') . "\n";
        echo "== 1 check: " . ($result['success'] == 1 ? 'true' : 'false') . "\n";
    }
    
} catch (Exception $e) {
    echo "Error: " . $e->getMessage() . "\n";
}
?>