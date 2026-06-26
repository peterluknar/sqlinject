<?php
/**
 * Adminer auto-login plugin for the demo stack.
 *
 * Hardcodes the MySQL connection so the user can just open Adminer and click
 * "Login" (no need to type server / username / password). Demo only — never
 * ship hardcoded credentials in a real Adminer deployment.
 */
class AdminerAutoLogin {
    /** server, username, password used for the actual connection */
    function credentials() {
        return array('db', 'app', 'app');
    }

    /** preselect the application database */
    function database() {
        return 'app';
    }

    /** accept the login regardless of what was typed in the form */
    function login($login, $password) {
        return true;
    }
}

return new AdminerAutoLogin;
