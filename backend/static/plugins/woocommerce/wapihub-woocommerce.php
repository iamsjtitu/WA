<?php
/**
 * Plugin Name: WapiHub WhatsApp for WooCommerce
 * Description: Sends WhatsApp notifications via WapiHub on order events.
 * Version: 1.0.0
 * Author: WapiHub
 */

if (!defined("ABSPATH")) {
    exit;
}

// ---- Settings page ----
add_action("admin_menu", function () {
    add_options_page(
        "WapiHub",
        "WapiHub",
        "manage_options",
        "wapihub",
        "wapihub_settings_page"
    );
});

add_action("admin_init", function () {
    register_setting("wapihub", "wapihub_api_base");
    register_setting("wapihub", "wapihub_api_key");
    register_setting("wapihub", "wapihub_template_paid");
    register_setting("wapihub", "wapihub_template_processing");
});

function wapihub_settings_page()
{
    ?>
    <div class="wrap">
        <h1>WapiHub WhatsApp</h1>
        <form method="post" action="options.php">
            <?php settings_fields("wapihub"); ?>
            <table class="form-table">
                <tr><th>API Base URL</th>
                    <td><input type="text" name="wapihub_api_base" size="60"
                        value="<?php echo esc_attr(get_option("wapihub_api_base")); ?>"
                        placeholder="https://your-wapihub.example.com/api" /></td></tr>
                <tr><th>API Key</th>
                    <td><input type="password" name="wapihub_api_key" size="60"
                        value="<?php echo esc_attr(get_option("wapihub_api_key")); ?>" /></td></tr>
                <tr><th>Order Paid Template</th>
                    <td><textarea name="wapihub_template_paid" rows="3" cols="60">
<?php echo esc_textarea(get_option("wapihub_template_paid", "Hi {{name}}, your order #{{order_id}} has been paid. Thank you!")); ?>
                    </textarea></td></tr>
                <tr><th>Processing Template</th>
                    <td><textarea name="wapihub_template_processing" rows="3" cols="60">
<?php echo esc_textarea(get_option("wapihub_template_processing", "Hi {{name}}, we're preparing order #{{order_id}}.")); ?>
                    </textarea></td></tr>
            </table>
            <?php submit_button(); ?>
        </form>
    </div>
    <?php
}

// ---- Helper ----
function wapihub_send($phone, $text, $url = null)
{
    $api_base = rtrim(get_option("wapihub_api_base"), "/");
    $api_key = get_option("wapihub_api_key");
    if (!$api_base || !$api_key) return false;

    $body = ["phonenumber" => $phone, "text" => $text];
    if ($url) $body["url"] = $url;

    return wp_remote_post($api_base . "/v2/sendMessage", [
        "timeout" => 20,
        "headers" => [
            "Authorization" => "Bearer " . $api_key,
        ],
        "body" => $body,
    ]);
}

function wapihub_render($template, $vars)
{
    foreach ($vars as $k => $v) {
        $template = str_replace("{{" . $k . "}}", (string) $v, $template);
    }
    return $template;
}

// ---- Hooks ----
add_action("woocommerce_order_status_completed", function ($order_id) {
    $order = wc_get_order($order_id);
    if (!$order) return;
    $phone = preg_replace("/[^0-9]/", "", $order->get_billing_phone());
    if (!$phone) return;
    $text = wapihub_render(
        get_option("wapihub_template_paid", "Order #{{order_id}} completed."),
        [
            "name" => $order->get_billing_first_name(),
            "order_id" => $order_id,
            "total" => $order->get_total(),
        ]
    );
    wapihub_send($phone, $text);
});

add_action("woocommerce_order_status_processing", function ($order_id) {
    $order = wc_get_order($order_id);
    if (!$order) return;
    $phone = preg_replace("/[^0-9]/", "", $order->get_billing_phone());
    if (!$phone) return;
    $text = wapihub_render(
        get_option("wapihub_template_processing", "Order #{{order_id}} received."),
        [
            "name" => $order->get_billing_first_name(),
            "order_id" => $order_id,
            "total" => $order->get_total(),
        ]
    );
    wapihub_send($phone, $text);
});
