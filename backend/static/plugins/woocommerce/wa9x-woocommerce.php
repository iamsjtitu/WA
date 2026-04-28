<?php
/**
 * Plugin Name: wa.9x.design WhatsApp for WooCommerce
 * Description: Sends WhatsApp notifications via wa.9x.design on order events.
 * Version: 1.0.0
 * Author: wa.9x.design
 */

if (!defined("ABSPATH")) {
    exit;
}

// ---- Settings page ----
add_action("admin_menu", function () {
    add_options_page(
        "wa.9x.design",
        "wa.9x.design",
        "manage_options",
        "wa9x",
        "wa9x_settings_page"
    );
});

add_action("admin_init", function () {
    register_setting("wa9x", "wa9x_api_base");
    register_setting("wa9x", "wa9x_api_key");
    register_setting("wa9x", "wa9x_template_paid");
    register_setting("wa9x", "wa9x_template_processing");
});

function wa9x_settings_page()
{
    ?>
    <div class="wrap">
        <h1>wa.9x.design WhatsApp</h1>
        <form method="post" action="options.php">
            <?php settings_fields("wa9x"); ?>
            <table class="form-table">
                <tr><th>API Base URL</th>
                    <td><input type="text" name="wa9x_api_base" size="60"
                        value="<?php echo esc_attr(get_option("wa9x_api_base")); ?>"
                        placeholder="https://your-wa9x.example.com/api" /></td></tr>
                <tr><th>API Key</th>
                    <td><input type="password" name="wa9x_api_key" size="60"
                        value="<?php echo esc_attr(get_option("wa9x_api_key")); ?>" /></td></tr>
                <tr><th>Order Paid Template</th>
                    <td><textarea name="wa9x_template_paid" rows="3" cols="60">
<?php echo esc_textarea(get_option("wa9x_template_paid", "Hi {{name}}, your order #{{order_id}} has been paid. Thank you!")); ?>
                    </textarea></td></tr>
                <tr><th>Processing Template</th>
                    <td><textarea name="wa9x_template_processing" rows="3" cols="60">
<?php echo esc_textarea(get_option("wa9x_template_processing", "Hi {{name}}, we're preparing order #{{order_id}}.")); ?>
                    </textarea></td></tr>
            </table>
            <?php submit_button(); ?>
        </form>
    </div>
    <?php
}

// ---- Helper ----
function wa9x_send($phone, $text, $url = null)
{
    $api_base = rtrim(get_option("wa9x_api_base"), "/");
    $api_key = get_option("wa9x_api_key");
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

function wa9x_render($template, $vars)
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
    $text = wa9x_render(
        get_option("wa9x_template_paid", "Order #{{order_id}} completed."),
        [
            "name" => $order->get_billing_first_name(),
            "order_id" => $order_id,
            "total" => $order->get_total(),
        ]
    );
    wa9x_send($phone, $text);
});

add_action("woocommerce_order_status_processing", function ($order_id) {
    $order = wc_get_order($order_id);
    if (!$order) return;
    $phone = preg_replace("/[^0-9]/", "", $order->get_billing_phone());
    if (!$phone) return;
    $text = wa9x_render(
        get_option("wa9x_template_processing", "Order #{{order_id}} received."),
        [
            "name" => $order->get_billing_first_name(),
            "order_id" => $order_id,
            "total" => $order->get_total(),
        ]
    );
    wa9x_send($phone, $text);
});
