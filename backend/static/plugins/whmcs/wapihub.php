<?php
/**
 * WapiHub WHMCS Module
 *
 * Drop into /modules/addons/wapihub/ inside your WHMCS install.
 * Activate from Setup → Addon Modules.
 */

if (!defined("WHMCS")) {
    die("This file cannot be accessed directly");
}

function wapihub_config()
{
    return [
        "name" => "WapiHub WhatsApp",
        "description" => "Send WhatsApp messages from WHMCS via WapiHub",
        "version" => "1.0",
        "author" => "WapiHub",
        "fields" => [
            "api_base" => [
                "FriendlyName" => "API Base URL",
                "Type" => "text",
                "Size" => "60",
                "Default" => "https://your-wapihub.example.com/api",
                "Description" => "Your WapiHub API base URL (no trailing slash)",
            ],
            "api_key" => [
                "FriendlyName" => "API Key",
                "Type" => "password",
                "Size" => "60",
                "Description" => "Your WapiHub API key (Bearer token)",
            ],
        ],
    ];
}

function wapihub_activate()
{
    return ["status" => "success", "description" => "WapiHub activated."];
}

function wapihub_deactivate()
{
    return ["status" => "success", "description" => "WapiHub deactivated."];
}

/**
 * Send a message helper. Use from hooks like:
 *   wapihub_send($vars, $phone, $text);
 */
function wapihub_send($vars, $phone, $text, $url = null)
{
    $api_base = rtrim($vars["api_base"], "/");
    $api_key = $vars["api_key"];
    $endpoint = $api_base . "/v2/sendMessage";

    $post = ["phonenumber" => $phone, "text" => $text];
    if ($url) {
        $post["url"] = $url;
    }

    $ch = curl_init($endpoint);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_HTTPHEADER => ["Authorization: Bearer " . $api_key],
        CURLOPT_POSTFIELDS => $post,
        CURLOPT_TIMEOUT => 20,
    ]);
    $resp = curl_exec($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    return ["status_code" => $code, "body" => $resp];
}

/**
 * Hook: send WhatsApp on invoice paid.
 * Place inside /includes/hooks/wapihub_invoice.php
 */
// add_hook("InvoicePaid", 1, function ($vars) {
//     $client = Capsule::table("tblclients")->where("id", $vars["userid"])->first();
//     if (!$client || !$client->phonenumber) return;
//     $config = getAddonVars("wapihub");
//     wapihub_send(
//         $config,
//         preg_replace("/[^0-9]/", "", $client->phonenumber),
//         "Hi {$client->firstname}, payment received for invoice #{$vars['invoiceid']}. Thank you!"
//     );
// });
