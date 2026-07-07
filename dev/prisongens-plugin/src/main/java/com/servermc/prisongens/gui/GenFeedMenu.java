package com.servermc.prisongens.gui;

import com.servermc.prisongens.PrisonGens;
import com.servermc.prisongens.gen.GenCategory;
import com.servermc.prisongens.managers.EconomyManager;
import com.servermc.prisongens.mine.MineManager;
import org.bukkit.Material;
import org.bukkit.Particle;
import org.bukkit.Sound;
import org.bukkit.entity.Player;
import org.bukkit.event.inventory.InventoryClickEvent;
import org.bukkit.inventory.ItemStack;

/**
 * Mejorar GEN: alimenta el GEN primario con otros GENS de tu inventario
 * para darle experiencia. También permite comprar Capacidad de Alimentación
 * extra para el propio ítem.
 */
public class GenFeedMenu extends Menu {

    private static final int TARGET_SLOT = 13;
    private static final int FEED_SLOT = 22;
    private static final int CAPACITY_SLOT = 31;
    private static final int BACK_SLOT = 40;

    public GenFeedMenu(PrisonGens plugin, Player viewer) {
        super(plugin, viewer, 45, "§a§l⬆ Mejorar GEN");
    }

    private long capacityCost() {
        return plugin.getGensConfig().getLong("capacity-upgrade-cost", 5000);
    }

    private int capacityAmount() {
        return plugin.getGensConfig().getInt("capacity-upgrade-amount", 5);
    }

    @Override
    protected void render() {
        fillBackground(Material.BLACK_STAINED_GLASS_PANE);

        ItemStack primary = plugin.getMineManager().getPrimaryGen(viewer.getUniqueId());
        if (primary == null) {
            inventory.setItem(TARGET_SLOT, item(Material.BARRIER, "§c§l✖ Sin GEN activo",
                    "", "§7Inserta un GEN en la sección de", "§7GENS antes de poder mejorarlo."));
        } else {
            ItemStack display = primary.clone();
            var meta = display.getItemMeta();
            var lore = meta.hasLore() ? new java.util.ArrayList<>(meta.getLore()) : new java.util.ArrayList<String>();
            lore.add("");
            lore.add("§6§l★ GEN PRIMARIO §7(recibe la XP)");
            meta.setLore(lore);
            display.setItemMeta(meta);
            inventory.setItem(TARGET_SLOT, display);
        }

        int fedInfo = primary != null ? plugin.getGenItemFactory().getFed(primary) : 0;
        int capInfo = primary != null ? plugin.getGenItemFactory().getCapacity(primary) : 0;
        inventory.setItem(FEED_SLOT, item(Material.EXPERIENCE_BOTTLE, "§a§l⬆ Alimentar GEN",
                "§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
                "§7Consume el primer GEN de tu",
                "§7inventario y transfiere su XP",
                "§7al GEN primario.",
                "",
                "§7GENS iguales: §fXP normal",
                "§7GENS inferiores: §fmenos XP",
                "§7GENS superiores: §fmucha más XP",
                "§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
                "§7Alimentados: §f" + fedInfo + "§7/§f" + capInfo,
                "",
                "§eClick para alimentar"));

        inventory.setItem(CAPACITY_SLOT, item(Material.HOPPER, "§6§l+ Capacidad de Alimentación",
                "§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
                "§7Aumenta permanentemente la",
                "§7capacidad de este GEN en §f+" + capacityAmount() + "§7.",
                "§7La mejora viaja con el ítem.",
                "§8▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
                "§7Costo: §6" + plugin.getEconomyManager().formatBalance(capacityCost()) + " Tokens",
                "",
                "§eClick para comprar"));

        inventory.setItem(BACK_SLOT, item(Material.ARROW, "§7← Volver"));
    }

    @Override
    public void onClick(InventoryClickEvent event) {
        switch (event.getSlot()) {
            case BACK_SLOT -> new MineAdminMenu(plugin, viewer).open();
            case FEED_SLOT -> feed();
            case CAPACITY_SLOT -> buyCapacity();
        }
    }

    private void feed() {
        MineManager.MineData mine = plugin.getMineManager().getMine(viewer.getUniqueId());
        ItemStack primary = plugin.getMineManager().getPrimaryGen(viewer.getUniqueId());
        if (primary == null) {
            deny("No tienes ningún GEN activo.");
            return;
        }

        // Buscar el primer GEN del inventario del jugador
        ItemStack food = null;
        for (ItemStack it : viewer.getInventory().getContents()) {
            if (it != null && plugin.getGenItemFactory().isGen(it)) { food = it; break; }
        }
        if (food == null) {
            deny("No tienes ningún GEN en tu inventario para alimentar.");
            return;
        }

        int fed = plugin.getGenItemFactory().getFed(primary);
        int cap = plugin.getGenItemFactory().getCapacity(primary);
        if (fed >= cap) {
            deny("Tu GEN alcanzó su capacidad de alimentación (" + cap + "). Compra más capacidad.");
            return;
        }

        GenCategory targetCat = plugin.getGenItemFactory().getCategory(primary);
        GenCategory foodCat = plugin.getGenItemFactory().getCategory(food);
        long gained = plugin.getGenItemFactory().computeFeedXp(targetCat, foodCat,
                plugin.getGenItemFactory().getLevel(food));

        int levelBefore = plugin.getGenItemFactory().getLevel(primary);
        if (!plugin.getGenItemFactory().feed(primary, food)) {
            deny("No se pudo alimentar el GEN.");
            return;
        }
        int levelAfter = plugin.getGenItemFactory().getLevel(primary);

        // Consumir el GEN comida
        food.setAmount(food.getAmount() - 1);

        // El primario vive en el slot de la mina: forzar recalculo de etapa
        plugin.getMineManager().onGensChanged(viewer.getUniqueId());
        plugin.getMineManager().saveData();

        success("GEN alimentado: §a+" + gained + " XP§7.");
        viewer.playSound(viewer.getLocation(), Sound.ENTITY_PLAYER_BURP, 0.6f, 1.4f);
        viewer.spawnParticle(Particle.HAPPY_VILLAGER, viewer.getLocation().add(0, 1.5, 0), 12, 0.4, 0.4, 0.4, 0);
        if (levelAfter > levelBefore) {
            viewer.sendMessage("§6§l★ §7¡Tu GEN subió a nivel §f" + levelAfter + "§7!");
            viewer.playSound(viewer.getLocation(), Sound.ENTITY_PLAYER_LEVELUP, 1f, 1.2f);
        }
        refresh();
    }

    private void buyCapacity() {
        ItemStack primary = plugin.getMineManager().getPrimaryGen(viewer.getUniqueId());
        if (primary == null) {
            deny("No tienes ningún GEN activo.");
            return;
        }
        if (!plugin.getEconomyManager().removeBalance(viewer, EconomyManager.TOKENS, capacityCost())) {
            deny("No tienes suficientes Tokens (" + plugin.getEconomyManager().formatBalance(capacityCost()) + ").");
            return;
        }
        plugin.getEconomyManager().saveData();
        plugin.getGenItemFactory().addCapBonus(primary, capacityAmount());
        plugin.getMineManager().onGensChanged(viewer.getUniqueId());
        plugin.getMineManager().saveData();
        success("Capacidad de alimentación aumentada en +" + capacityAmount() + ".");
        refresh();
    }
}
