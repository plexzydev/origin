package dev.plexzy.prisongens.commands;

import dev.plexzy.prisongens.PrisonGens;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;

import java.util.ArrayList;
import java.util.List;

public class PgAdminCommand implements CommandExecutor, TabCompleter {

    private final PrisonGens plugin;

    public PgAdminCommand(PrisonGens plugin) {
        this.plugin = plugin;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!sender.hasPermission("prisongens.admin")) {
            sender.sendMessage("§cNo tienes permiso para ejecutar este comando.");
            return true;
        }

        if (args.length == 0) {
            sender.sendMessage("§a--- PrisonGens Admin ---");
            sender.sendMessage("§e/pgadmin reload §7- Recarga la configuración");
            sender.sendMessage("§e/pgadmin save §7- Guarda todos los datos forzosamente");
            return true;
        }

        if (args[0].equalsIgnoreCase("reload")) {
            plugin.reloadConfig();
            sender.sendMessage("§aConfiguración recargada exitosamente.");
            return true;
        }

        if (args[0].equalsIgnoreCase("save")) {
            if (plugin.getRobotManager() != null) plugin.getRobotManager().saveAll();
            if (plugin.getGenManager() != null) plugin.getGenManager().saveAll();
            if (plugin.getUpgradeManager() != null) plugin.getUpgradeManager().saveAll();
            sender.sendMessage("§aTodos los datos han sido guardados manualmente.");
            return true;
        }

        sender.sendMessage("§cComando desconocido. Usa /pgadmin para ver la lista de comandos.");
        return true;
    }

    @Override
    public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        List<String> completions = new ArrayList<>();
        if (args.length == 1 && sender.hasPermission("prisongens.admin")) {
            completions.add("reload");
            completions.add("save");
        }
        return completions;
    }
}
