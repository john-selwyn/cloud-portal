<?php
// Included only within Hestia's authenticated Web Domains page.
if (!defined('HESTIA_CMD') || empty($_SESSION['user']) || empty($username)) { return; }
if (($_SESSION['userContext'] ?? '') === 'admin' && empty($_SESSION['look'])) { return; }
if (!preg_match('/\A[a-z][a-z0-9_-]{0,31}\z/D', $username)) { return; }
$ict_config = json_decode(file_get_contents('/usr/local/share/ict-hosting-ui/access.json'), true);
if (!is_array($ict_config) || empty($ict_config['host']) || empty($ict_config['fingerprint'])) { return; }
$ict_escape = static function ($value) { return htmlspecialchars((string)$value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); };
$ict_shell = basename($_SESSION['login_shell'] ?? 'nologin');
$ict_ssh = in_array($ict_shell, ['jailbash', 'bash', 'sh', 'dash', 'rbash'], true);
$ict_host = $ict_config['host'];
$ict_port = (int)$ict_config['port'];
$ict_sftp = 'sftp -P ' . $ict_port . ' ' . $username . '@' . $ict_host;
$ict_ssh_command = 'ssh -p ' . $ict_port . ' ' . $username . '@' . $ict_host;
?>
<link rel="stylesheet" href="/css/custom/ict-connections.css">
<section class="container ict-connections" aria-labelledby="ict-connections-title">
<h2 id="ict-connections-title">SSH / SFTP connection details</h2>
<p><?= $ict_ssh ? 'SSH terminal and SFTP file access' : 'SFTP file access; interactive SSH is disabled' ?></p>
<dl>
<?php foreach (['Host' => $ict_host, 'Port' => $ict_port, 'Hosting username' => $username] as $ict_label => $ict_value) { ?>
<div><dt><?= $ict_escape($ict_label) ?></dt><dd><code><?= $ict_escape($ict_value) ?></code> <button type="button" data-ict-copy="<?= $ict_escape($ict_value) ?>">Copy <?= $ict_escape(strtolower($ict_label)) ?></button></dd></div>
<?php } ?>
</dl>
<p>Use your hosting password or an SSH key added to this account. Your password is not displayed here.</p>
<details><summary>FileZilla / WinSCP</summary><p>Select <strong>SFTP</strong>, use the host, port and username above, then authenticate with your hosting password or configured key.</p></details>
<details><summary>Website folders</summary>
<?php foreach (array_keys($data ?? []) as $ict_domain) {
    if (!preg_match('/\A[a-zA-Z0-9.-]+\z/D', $ict_domain)) { continue; }
    $ict_path = '/home/' . $username . '/web/' . $ict_domain . '/public_html'; ?>
<p><code><?= $ict_escape($ict_path) ?></code> <button type="button" data-ict-copy="<?= $ict_escape($ict_path) ?>">Copy folder</button></p>
<?php } ?>
<p>Use the domain's configured document root if it was customized for your application.</p>
</details>
<details><summary>Terminal commands</summary><p><code><?= $ict_escape($ict_sftp) ?></code> <button type="button" data-ict-copy="<?= $ict_escape($ict_sftp) ?>">Copy SFTP command</button></p>
<?php if ($ict_ssh) { ?><p><code><?= $ict_escape($ict_ssh_command) ?></code> <button type="button" data-ict-copy="<?= $ict_escape($ict_ssh_command) ?>">Copy SSH command</button></p><?php } ?>
</details>
<details><summary>Verify your first connection</summary><p>Compare the server's ED25519 fingerprint before accepting its key. If it differs, stop and contact support.</p><p><code><?= $ict_escape($ict_config['fingerprint']) ?></code> <button type="button" data-ict-copy="<?= $ict_escape($ict_config['fingerprint']) ?>">Copy fingerprint</button></p></details>
<p id="ict-copy-status" role="status" aria-live="polite"></p>
</section>
<script src="/js/custom/ict-connections.js" defer></script>
