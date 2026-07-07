package com.servermc.lobby.commands;

import com.servermc.lobby.LobbyCore;
import com.servermc.lobby.managers.NPCManager;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.TextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

import java.util.Set;

/**
 * /npc command - Manages NPC server selectors.
 * 
 * Subcommands:
 *   /npc create <id> <displayName> <serverName>  - Creates an NPC at player's location
 *   /npc delete <id>                              - Deletes an NPC
 *   /npc list                                     - Lists all NPCs
 *   /npc setserver <id> <serverName>              - Changes the target server
 */
public class NPCCommand implements CommandExecutor {

    private final LobbyCore plugin;

    private static final TextColor GREEN = TextColor.color(85, 255, 85);
    private static final TextColor RED = TextColor.color(255, 85, 85);
    private static final TextColor CYAN = TextColor.color(85, 255, 255);
    private static final TextColor GRAY = TextColor.color(170, 170, 170);
    private static final TextColor WHITE = TextColor.color(255, 255, 255);
    private static final TextColor GOLD = TextColor.color(255, 170, 0);
    private static final TextColor DARK_GRAY = TextColor.color(85, 85, 85);
    private static final TextColor YELLOW = TextColor.color(255, 255, 85);

    public NPCCommand(LobbyCore plugin) {
        this.plugin = plugin;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage("Este comando solo puede ser ejecutado por un jugador.");
            return true;
        }

        if (!player.hasPermission("lobby.admin")) {
            player.sendMessage(Component.empty()
                    .append(Component.text(" ❌ ", RED))
                    .append(Component.text("No tienes permisos.", RED)));
            return true;
        }

        if (args.length == 0) {
            sendHelp(player);
            return true;
        }

        NPCManager npcManager = plugin.getNpcManager();
        String sub = args[0].toLowerCase();

        switch (sub) {
            case "create" -> {
                if (args.length < 4) {
                    player.sendMessage(Component.empty()
                            .append(Component.text(" ❌ ", RED))
                            .append(Component.text("Uso: /npc create <id> <nombre> <servidor> [skin]", WHITE)));
                    return true;
                }

                String id = args[1].toLowerCase();
                String displayName = args[2].replace("_", " ");
                String serverName = args[3];
                String skin = args.length >= 5 ? args[4] : "Steve";

                boolean created = npcManager.createNPC(id, displayName, serverName, player.getLocation(), skin);
                if (created) {
                    player.sendMessage(Component.empty()
                            .append(Component.text(" ✅ ", GREEN))
                            .append(Component.text("NPC ", GRAY))
                            .append(Component.text(displayName, CYAN).decoration(TextDecoration.BOLD, true))
                            .append(Component.text(" creado → ", GRAY))
                            .append(Component.text(serverName, YELLOW))
                            .append(Component.text(" (skin: " + skin + ")", GRAY)));
                } else {
                    player.sendMessage(Component.empty()
                            .append(Component.text(" ❌ ", RED))
                            .append(Component.text("Ya existe un NPC con el id '", RED))
                            .append(Component.text(id, WHITE))
                            .append(Component.text("'.", RED)));
                }
            }

            case "delete" -> {
                if (args.length < 2) {
                    player.sendMessage(Component.empty()
                            .append(Component.text(" ❌ ", RED))
                            .append(Component.text("Uso: /npc delete <id>", WHITE)));
                    return true;
                }

                String id = args[1].toLowerCase();
                boolean deleted = npcManager.deleteNPC(id);
                if (deleted) {
                    player.sendMessage(Component.empty()
                            .append(Component.text(" ✅ ", GREEN))
                            .append(Component.text("NPC eliminado: ", GRAY))
                            .append(Component.text(id, CYAN)));
                } else {
                    player.sendMessage(Component.empty()
                            .append(Component.text(" ❌ ", RED))
                            .append(Component.text("NPC no encontrado: ", RED))
                            .append(Component.text(id, WHITE)));
                }
            }

            case "list" -> {
                Set<String> ids = npcManager.getAllNPCIds();
                if (ids.isEmpty()) {
                    player.sendMessage(Component.empty()
                            .append(Component.text(" ℹ ", CYAN))
                            .append(Component.text("No hay NPCs creados.", GRAY)));
                } else {
                    player.sendMessage(Component.empty()
                            .append(Component.text(" 📋 NPCs del Lobby ", GOLD).decoration(TextDecoration.BOLD, true))
                            .append(Component.text("(" + ids.size() + ")", GRAY)));

                    for (String id : ids) {
                        String info = npcManager.getNPCInfo(id);
                        player.sendMessage(Component.empty()
                                .append(Component.text("  ▸ ", DARK_GRAY))
                                .append(Component.text(id, CYAN))
                                .append(Component.text(" - ", DARK_GRAY))
                                .append(Component.text(info != null ? info : "Sin info", GRAY)));
                    }
                }
            }

            case "setserver" -> {
                if (args.length < 3) {
                    player.sendMessage(Component.empty()
                            .append(Component.text(" ❌ ", RED))
                            .append(Component.text("Uso: /npc setserver <id> <servidor>", WHITE)));
                    return true;
                }

                String id = args[1].toLowerCase();
                String server = args[2];
                boolean updated = npcManager.setServer(id, server);
                if (updated) {
                    player.sendMessage(Component.empty()
                            .append(Component.text(" ✅ ", GREEN))
                            .append(Component.text("Servidor actualizado: ", GRAY))
                            .append(Component.text(id, CYAN))
                            .append(Component.text(" → ", DARK_GRAY))
                            .append(Component.text(server, YELLOW)));
                } else {
                    player.sendMessage(Component.empty()
                            .append(Component.text(" ❌ ", RED))
                            .append(Component.text("NPC no encontrado: ", RED))
                            .append(Component.text(id, WHITE)));
                }
            }

            case "setskin" -> {
                if (args.length < 3) {
                    player.sendMessage(Component.empty()
                            .append(Component.text(" ❌ ", RED))
                            .append(Component.text("Uso: /npc setskin <id> <jugadorPremium>", WHITE)));
                    return true;
                }

                String id = args[1].toLowerCase();
                String skinName = args[2];
                boolean updated = npcManager.setSkin(id, skinName);
                if (updated) {
                    player.sendMessage(Component.empty()
                            .append(Component.text(" ✅ ", GREEN))
                            .append(Component.text("Skin actualizada: ", GRAY))
                            .append(Component.text(id, CYAN))
                            .append(Component.text(" → ", DARK_GRAY))
                            .append(Component.text(skinName, YELLOW)));
                } else {
                    player.sendMessage(Component.empty()
                            .append(Component.text(" ❌ ", RED))
                            .append(Component.text("NPC no encontrado: ", RED))
                            .append(Component.text(id, WHITE)));
                }
            }

            default -> sendHelp(player);
        }

        return true;
    }

    private void sendHelp(Player player) {
        player.sendMessage(Component.empty());
        player.sendMessage(Component.text(" ⚙ Comandos NPC", GOLD).decoration(TextDecoration.BOLD, true));
        player.sendMessage(Component.empty()
                .append(Component.text("  /npc create <id> <nombre> <servidor> [skin]", CYAN))
                .append(Component.text(" - Crea un NPC", GRAY)));
        player.sendMessage(Component.empty()
                .append(Component.text("  /npc delete <id>", CYAN))
                .append(Component.text(" - Elimina un NPC", GRAY)));
        player.sendMessage(Component.empty()
                .append(Component.text("  /npc list", CYAN))
                .append(Component.text(" - Lista todos los NPCs", GRAY)));
        player.sendMessage(Component.empty()
                .append(Component.text("  /npc setserver <id> <servidor>", CYAN))
                .append(Component.text(" - Cambia el servidor", GRAY)));
        player.sendMessage(Component.empty()
                .append(Component.text("  /npc setskin <id> <jugadorPremium>", CYAN))
                .append(Component.text(" - Cambia la skin", GRAY)));
        player.sendMessage(Component.empty());
    }
}
